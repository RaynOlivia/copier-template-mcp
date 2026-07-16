import yaml
import copier
from git import Repo
from shutil import rmtree
from os import path, listdir, makedirs

TEMPLATES_DIR = 'templates'
VALID_YAMLS = [
    'copier.yaml',
    'copier.yml',
]


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

