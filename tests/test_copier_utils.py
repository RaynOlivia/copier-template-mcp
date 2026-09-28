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

import os
import shutil
# import pytest
import copier_utils

copier_utils.TEMPLATES_DIR = os.path.join('testassets', 'templates')
copier_utils.TEMPLATES_FILE = os.path.join(copier_utils.TEMPLATES_DIR, 'templates.yaml')


def test_load_yaml():
    nonyam = copier_utils.load_yaml('nonexist.yaml')
    assert nonyam is None, f'non-existent yaml file returned not None: {nonyam}'
    
    yam = copier_utils.load_yaml(os.path.join('testassets', 'testyam.yml'))
    assert yam.get('a') == 'this is a test string', f'a has wrong value: {yam.get("a")}'
    
    b = yam.get('b')
    assert isinstance(b, dict), 'b is not a dictionary'
    assert b.get('ba') == 13.37, f'b["ba"] has wrong value: {b.get("ba")}'
    assert b.get('bb') == 44, f'b["bb"] has wrong value: {b.get("bb")}'
    
    c = yam.get('c')
    assert isinstance(c, list), 'c is not a list'
    assert len(c) > 2, 'c is missing some elements'
    assert c[0] == 'uwu', f'c[0] has wrong value: {c[0]}'
    assert c[1] == 'owo', f'c[1] has wrong value: {c[1]}'
    assert c[2] == False, f'c[2] has wrong value: {c[2]}'


def test_get_templates():
    yam = copier_utils.get_templates()
    assert isinstance(yam, dict), 'templates file is not a dict'
    template = yam.get('copier-pylib')
    assert template is not None, '"copier-pylib" not found in list'
    assert template.get('path') == 'copier-pylib-test', f'path has wrong value: {template.get('path')}'
    assert template.get('description') == 'testing version of copier-pylib template', f'description has wrong value: {template.get('path')}'


def test_add_template():
    try:
        copier_utils.add_template('testytemplate', 'uwu/owo/testytemplate', 'a made up template for testing')
        yam = copier_utils.get_templates()
        new_temp = yam.get('testytemplate')
        assert new_temp is not None, 'failed to add template to list'
        assert new_temp.get('path') == 'uwu/owo/testytemplate', f'path has wrong value: {new_temp.get('path')}'
        assert new_temp.get('description') == 'a made up template for testing', f'description has wrong value: {new_temp.get('path')}'
    finally:
        os.remove(copier_utils.TEMPLATES_FILE)
        shutil.copyfile(copier_utils.TEMPLATES_FILE + '.orig', copier_utils.TEMPLATES_FILE)


def test_get_template_path():
    path = copier_utils.get_template_path('copier-pylib')
    assert path == os.path.abspath(os.path.join(copier_utils.TEMPLATES_DIR, 'copier-pylib-test')), f'wrong template path: {path}'

