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


def get_params(name: str) -> list:
    yam = get_copier_file(name)
    if yam is None:
        raise Exception('copier.yaml file does not exist')

    out = {}
    for key in yam:
        if key[0] == '_':
            continue
        
        out[key] = {}
        if 'type' in yam[key]:
            out[key]['type'] = yam[key]['type']
        if 'help' in yam[key]:
            out[key]['description'] = yam[key]['help']
        #TODO: add choices if available

    return out


def generate(name: str, dst_path: str, params: dict):
    if path.exists(dst_path):
        rmtree(dst_path)
    makedirs(dst_path, exist_ok = True)
    copier.run_copy(
        src_path = path.join(TEMPLATES_DIR, name),
        dst_path = dst_path,
        data = params,
        overwrite = True,
        quiet = True,
        skip_tasks = True,
    )


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

        self.proc = mp.Process(target = self._run_copy_proc, args = [self._in_q, self._out_q])
        log.debug('starting process..')
        self.proc.start()
        log.debug('generator initialized')


    def __del__(self):
        self.cancel()


    def next_question(self) -> (dict|None, str|None):
        try:
            log.debug('client requested next question')
            a, b = self._out_q.get()
            log.debug(f'client got response!')
            if a is not None:
                return cloudpickle.loads(a), b
            else:
                return None, b
        except ValueError:
            log.debug('queue closed while reading!')
            return None, None


    def respond(self, reply: str) -> bool:
        try:
            self._in_q.put(reply)
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


    def _io_handler(self, in_queue, out_queue, questions, answers, **kwargs):
        question = questions[0]
        log.debug(f'NEW QUESTION: {question['name']}')
        if not question['when']('nya~'):
            log.debug('skipping question')
            return {}

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


    def _run_copy_proc(self, in_queue, out_queue):
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

        log.debug('post patch. closing queues')
        out_queue.close()
        in_queue.close()