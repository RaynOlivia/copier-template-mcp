import yaml
import copier
import cloudpickle
from git import Repo
from shutil import rmtree
from unittest.mock import patch
from os import path, listdir, makedirs
from functools import partial
import multiprocessing as mp
import logging
import queue
import time

TEMPLATES_DIR = 'templates'
VALID_YAMLS = [
    'copier.yaml',
    'copier.yml',
]

log = logging.Logger('Copier')
log.addHandler(logging.FileHandler('copier.log', mode='a'))
log.setLevel(10)


def get_copier_file(name: str) -> dict | None:
    for filename in VALID_YAMLS:
        filepath = path.join(TEMPLATES_DIR, name, filename)
        if path.isfile(filepath):
            try:
                with open(filepath, 'r') as file:
                    yam = yaml.safe_load(file)
            except Exception:
                pass
            else:
                return yam
    return None


def get_templates() -> list[str]:
    return [
        name for name in listdir(TEMPLATES_DIR) \
        if get_copier_file(name) is not None
    ]


def clone_template(uri: str, name: str):
    dst_path = path.join(TEMPLATES_DIR, name)
    # if path.exists(dst_path):
    #     rmtree(dst_path)
    Repo.clone_from(uri, dst_path)


class Generator():
    def __init__(self, template: str, dst_path: str):
        self.template = template
        self.dst_path = dst_path

        self._in_q = mp.Queue()
        self._out_q = mp.Queue()

        self.proc = mp.Process(target = self._run_copy_proc)
        self.proc.start()
        self.current_question = None
        self.last_answer = None
        self.data = {}
        log.debug('generator initialized')


    def __del__(self):
        self.cancel()


    def next_question(self) -> (dict|None, str|None):
        try:
            while True:
                try:
                    a, b = self._out_q.get_nowait()
                    break
                except queue.Empty:
                    if self.proc.is_alive():
                        time.sleep(1)
                    else:
                        log.debug('proc has closed. saving last response')
                        self._log_data()
                        self.current_question = None
                        return None, None
            if b is None:
                self._log_data()

            if a is not None:
                self.current_question = cloudpickle.loads(a)
            else:
                self.current_question = None
            return self.current_question, b
        except Exception:
            log.debug('queue closed while reading!')

        self._log_data()
        self.current_question = None
        return None, None


    def respond(self, reply: str|list[str]) -> bool:
        try:
            self._in_q.put(reply)
            self.last_answer = reply
            return True
        except ValueError:
            return False


    def join(self) -> None:
        return self.proc.join()


    def cancel(self) -> None:
        if self.proc.is_alive():
            self.proc.kill()
        self._out_q.close()
        self._in_q.close()
        return self.join()


    def generate(self):
        if path.exists(self.dst_path):
            rmtree(self.dst_path)
        makedirs(self.dst_path, exist_ok = True)
        copier.run_copy(
            src_path = path.join(TEMPLATES_DIR, self.template),
            dst_path = self.dst_path,
            data = {key: val['answer'] for key, val in self.data.items()},
            overwrite = True,
            quiet = True,
            skip_tasks = True,
        )


    def _log_data(self):
        if self.current_question is not None and self.last_answer is not None:
            self.data[self.current_question['name']] = {'answer': self.last_answer, 'question': self.current_question}


    def _io_handler(self, in_queue, out_queue, questions, answers, **kwargs):
        question = questions[0]
        log.debug(f'NEW QUESTION: {question['name']}')
        # if not question['when']('nya~'):
        #     log.debug('skipping question')
        #     return {}

        log.debug('writing to queue')
        out_queue.put((cloudpickle.dumps(question), None))
        log.debug('waiting for client reply')
        reply = in_queue.get()
        log.debug(f'got response: {reply}')

        validator = question.get('validate')
        if callable(validator):
            verdict = validator(reply)
            while verdict is not True:
                out_queue.put((cloudpickle.dumps(question), verdict))
                reply = in_queue.get()
                verdict = validator(reply)

        out_filter = question.get('filter', lambda x: x)
        return {question['name']: out_filter(reply)}


    def _run_copy_proc(self):
        if path.exists(self.dst_path):
            rmtree(self.dst_path)
        makedirs(self.dst_path, exist_ok = True)
        log.debug('pre patch')
        with patch('copier._main.unsafe_prompt', new = partial(self._io_handler, self._in_q, self._out_q)):
            log.debug('running copy...')
            copier.run_copy(
                src_path = path.join(TEMPLATES_DIR, self.template),
                dst_path = self.dst_path,
                overwrite = True,
                quiet = True,
                pretend = True,
            )
            log.debug('ran copy!')

        log.debug('post patch. closing queues')
        self._out_q.close()
        self._in_q.close()
        log.debug('queues closed. process is done')