import yaml
import copier
import shutil
from git import Repo
from os import path, listdir

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

    out = []
    for key in yam:
        if key[0] == '_':
            continue
        param = {'name': key}
        if 'type' in yam[key]:
            param['type'] = yam[key]['type']
        if 'help' in yam[key]:
            param['description'] = yam[key]['help']
        #TODO: add choices if available
        out.append(param)

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
    dest = path.join(TEMPLATES_DIR, name)
    if path.exists(dest):
        shutil.rmtree(dest)
    Repo.clone_from(uri, dest)

