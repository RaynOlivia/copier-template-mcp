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

import pytest
import server
import os
from fastmcp.client import Client
from fastmcp.client.elicitation import ElicitResult
from tests.fixtures import tmp_template_dir


_elicit_responses = []
_elicit_questions = []

async def _elicitation_handler(message, response_type, params, context):
    _elicit_questions.append([message, response_type])

    if len(_elicit_responses) < 1:
        return ElicitResult(action = 'decline')
    
    resp = _elicit_responses.pop()
    print(f'aaaaa  {resp}')
    return response_type(value = resp[1])


@pytest.fixture
async def client():
    async with Client(
        transport = server.mcp,
        elicitation_handler = _elicitation_handler,
    ) as mcp_client:
        yield mcp_client


async def test_tools_list(client):
    result = await client.list_tools()
    tool_names = [t.name for t in result]

    assert len(tool_names) == 6
    assert 'start_project' in tool_names
    assert 'update_project' in tool_names
    assert 'set_next_parameter' in tool_names
    assert 'search_github_for_templates' in tool_names
    assert 'add_template' in tool_names
    assert 'list_templates' in tool_names


@pytest.mark.asyncio
async def test_generate_project(client, tmp_template_dir):
    global _elicit_responses
    dst_path = os.path.join(tmp_template_dir, '..', 'dist')

    res = await client.call_tool('start_project', {'template': 'sample_tmplt', 'destination': dst_path})
    assert res.data.get('next_question') == 'Name of project'

    res = await client.call_tool('set_next_parameter', {'response': 'proj_in_testing'})
    assert res.data.get('next_question') == 'Number of eels'
    
    res = await client.call_tool('set_next_parameter', {'response': '9'})
    assert res.data.get('next_question') == 'Estimated snack expenses to complete project'

    res = await client.call_tool('set_next_parameter', {'response': '10.02'})
    assert res.data.get('next_question') == 'Do you like hotdog?'

    res = await client.call_tool('set_next_parameter', {'response': 'no'})
    assert res.data.get('next_question') == 'A path'

    res = await client.call_tool('set_next_parameter', {'response': 'conf'})
    assert res.data.get('next_question') == 'Extra YAML data'

    res = await client.call_tool('set_next_parameter', {'response': r'x: uwu'})
    assert res.data.get('next_question') == 'Extra JSON data'

    res = await client.call_tool('set_next_parameter', {'response': r'{"y": "UwU", "yy": "OwO"}'})
    assert res.data.get('next_question') == 'Who pays for the snacks?'

    res = await client.call_tool('set_next_parameter', {'response': 'jeff'})
    assert res.data.get('next_question') == 'Config file name'

    res = await client.call_tool('set_next_parameter', {'response': 'conf/settings.conf'})
    assert res.data.get('next_question') == 'Pick your lucky numbers'

    _elicit_responses = [
        ['accept', ['project_name', 'eels', 'hottodogu']],
        ['accept', {
            'project_name': 'testing_project',
            'eels': '14',
            'hottodogu': 'yes',
        }],
    ]

    res = await client.call_tool('set_next_parameter', {'response': ['1', '42', '1312']})
    assert res.content[0].text[:31] == 'Project created successfully at'

    print(len(_elicit_questions))
    for q in _elicit_questions:
        print(f'{q[0]} - {q[1]}')

    assert os.path.isdir(os.path.join(dst_path, 'proj_in_testing'))
