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
import server
import copier_utils
from fastmcp.client import Client
from fastmcp.client.elicitation import ElicitResult


class _TestClient(Client):
    def __init__(self):
        self.elicit_responses = []
        self.elicit_questions = []
        super().__init__(
            transport = server.mcp,
            elicitation_handler = self._elicitation_handler,
        )


    async def _elicitation_handler(self, message, response_type, params, context):
        self.elicit_questions.append([message, response_type])

        if len(self.elicit_responses) < 1:
            return ElicitResult(action = 'decline')
        
        resp = self.elicit_responses.pop()
        return ElicitResult(
            action = resp[0],
            content = response_type(**resp[1])
        )


@pytest.fixture
async def mcp_client():
    """Provides fastmcp Client linked to a new server instance
    Client object includes simple user elicitation handler
    """

    async with _TestClient() as client:
        yield client


@pytest.fixture
def tmp_template_dir(tmp_path):
    """Provides path to a fresh temporary directory containing a copy of tests/assets/templates
    Warning: changes copier_utils.TEMPLATES_DIR and .TEMPLATES_FILE to use the temporary copy
    """

    skel_path = os.path.join('tests', 'assets', 'templates')
    templates_path = os.path.join(tmp_path, 'templates')

    shutil.copytree(skel_path, templates_path)

    copier_utils.TEMPLATES_DIR = templates_path
    copier_utils.TEMPLATES_FILE = os.path.join(copier_utils.TEMPLATES_DIR, 'templates.yaml')
    return tmp_path
