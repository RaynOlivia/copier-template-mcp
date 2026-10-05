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
import pytest
import copier_utils


@pytest.fixture
def tmp_template_dir(tmp_path):
    skel_path = os.path.join('tests', 'assets', 'templates')
    templates_path = os.path.join(tmp_path, 'templates')

    shutil.copytree(skel_path, templates_path)

    copier_utils.TEMPLATES_DIR = templates_path
    copier_utils.TEMPLATES_FILE = os.path.join(copier_utils.TEMPLATES_DIR, 'templates.yaml')
    return copier_utils.TEMPLATES_DIR
