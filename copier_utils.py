# CopierMCP - An MCP server for using Copier-templates
# Copyright (C) 2026 Rayn Hochhalter

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/gpl-3.0.html>.

from shutil import rmtree
from unittest.mock import patch
from os import path, makedirs
from functools import partial
import multiprocessing as mp
import logging
import queue
import time
import git
import yaml
import copier
import cloudpickle

TEMPLATES_DIR = 'templates'
TEMPLATES_FILE = path.join(TEMPLATES_DIR, 'templates.yaml')

log = logging.Logger('Copier')
log.addHandler(logging.FileHandler('copier.log', mode='a'))
log.setLevel(10)


def load_yaml(file_path: str) -> dict|None:
    base_path, file_name = path.split(path.normpath(file_path))
    if not path.isdir(base_path):
        return None
    file_base, _ = path.splitext(file_name)

    options = [file_path]
    for ext in ('.yaml', '.yml'):
        new_opt = path.join(base_path, file_base + ext)
        if not new_opt in options:
            options.append(new_opt)

    for opt_path in options:
        if path.isfile(opt_path):
            try:
                with open(opt_path, 'r') as file:
                    yam = yaml.safe_load(file)
            except Exception:
                pass
            else:
                return yam
    return None


def get_templates() -> dict:
    return load_yaml(TEMPLATES_FILE) or {}


def add_template(name, path, description) -> None:
    new_template = {'path': path, 'description': description}
    templates = get_templates()
    templates[name] = new_template
    with open(TEMPLATES_FILE, 'w') as file:
        yaml.dump(templates, file)


def get_template_path(template):
    template_path = get_templates().get(template, {}).get('path')
    if not template_path:
        return None

    elif not path.isabs(template_path) and load_yaml(path.join(TEMPLATES_DIR, template_path, 'copier.yaml')) is not None:
        return path.abspath(path.join(TEMPLATES_DIR, template_path))

    elif load_yaml(path.join(template_path, 'copier.yaml')) is not None:
        return path.abspath(template_path)

    try:
        git.cmd.Git().ls_remote(template_path)
    except Exception:
        return None
    else:
        return template_path


class Generator():
    def __init__(self, template: str, dst_path: str, update: bool = False):
        self.template = template
        self.dst_path = dst_path
        self.update = update

        self._in_q = mp.Queue()
        self._out_q = mp.Queue()

        if self.update:
            if load_yaml(path.join(self.dst_path, '.copier-answers.yml')) is None:
                raise Exception('project is not generated from copier template')
            try:
                self.repo = git.Repo(self.dst_path)
            except git.exc.InvalidGitRepositoryError:
                try:
                    log.debug('creating git repo')
                    self.repo = git.Repo.init(self.dst_path)
                    self.repo.git.add(all = True)
                    self.repo.index.commit('initial commit')
                except Exception as e:
                    raise Exception(f'failed to initialize git repo: {e}')
            except git.exc.NoSuchPathError:
                raise Exception('invalid project path')
        else:
            self.template_path = get_template_path(self.template)

        self.proc = mp.Process(target = self._run_copy_proc)
        self.proc.start()
        self.current_question = None
        self.last_answer = None
        self.data = {}
        log.debug('generator initialized')


    def __del__(self):
        self.cancel()


    def get_merge_conflicts(self) -> list[str]:
        return list(self.repo.index.unmerged_blobs().keys())


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
        if self.update:
            copier.run_update(
                dst_path = self.dst_path,
                data = {key: val['answer'] for key, val in self.data.items()},
                overwrite = True,
                quiet = True,
                # skip_tasks = True,
                skip_answered = True,
                conflict = 'inline',
            )
        else:
            if path.exists(self.dst_path):
                rmtree(self.dst_path)
            makedirs(self.dst_path, exist_ok = True)
            copier.run_copy(
                src_path = self.template_path,
                dst_path = self.dst_path,
                data = {key: val['answer'] for key, val in self.data.items()},
                overwrite = True,
                quiet = True,
                # skip_tasks = True,
            )


    def _log_data(self):
        if self.current_question is not None and self.last_answer is not None:
            self.data[self.current_question['name']] = {'answer': self.last_answer, 'question': self.current_question}


    def _io_handler(self, in_queue, out_queue, questions, answers, **kwargs):
        question = questions[0]
        if not question.get("when", lambda x: True)(666):
            log.debug(f'QUESTION SKIPPED: {question["name"]}')
            return {question['name']: ''}
        log.debug(f'NEW QUESTION: {question["name"]}')
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
        log.debug('pre patch')
        with patch('copier._main.unsafe_prompt', new = partial(self._io_handler, self._in_q, self._out_q)):
            if self.update:
                log.debug('running update...')
                copier.run_update(
                    dst_path = self.dst_path,
                    skip_answered = True,
                    overwrite = True,
                    quiet = True,
                    pretend = True,
                )
                log.debug('ran update!')

            else:
                if path.exists(self.dst_path):
                    rmtree(self.dst_path)
                makedirs(self.dst_path, exist_ok = True)
                log.debug('running copy...')
                copier.run_copy(
                    src_path = self.template_path,
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