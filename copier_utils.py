#!./venv/bin/python3

import sys
import yaml
import copier
import shutil
import asyncio
from git import Repo
from os import path, listdir



TEMPLATES_DIR = 'templates'

def get_templates():
    return [
        name for name in listdir(TEMPLATES_DIR) \
        if path.exists(path.join(TEMPLATES_DIR, name, 'copier.yaml'))
    ]


def get_params(name: str):
    templatepath = path.join(TEMPLATES_DIR, name, 'copier.yaml')

    if not path.exists(templatepath):
        raise Exception('copier.yaml not exist')

    yam = {}
    out = {}
    with open(templatepath, 'r') as file:
        yam = yaml.safe_load(file)

    for key in yam:
        if key[0] == '_':
            continue
        out[key] = {}
        if 'help' in yam[key]:
            out[key]['description'] = yam[key]['help']
        if 'type' in yam[key]:
            out[key]['type'] = yam[key]['type']

    return out


def generate(name: str, dst_path: str, params: dict):
    copier.run_copy(
        src_path = path.join(TEMPLATES_DIR, name),
        dst_path = dst_path,
        data = params,
        overwrite = True,
        quiet = True,
    )


def clone_template(uri: str, name: str):
    Repo.clone_from(uri, path.join(TEMPLATES_DIR, name))
