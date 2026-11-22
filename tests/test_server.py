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
import os
from tests.fixtures import tmp_template_dir, mcp_client


async def test_tools_list(mcp_client):
    result = await mcp_client.list_tools()
    tool_names = [t.name for t in result]

    assert len(tool_names) == 6
    assert 'start_project' in tool_names
    assert 'update_project' in tool_names
    assert 'set_next_parameter' in tool_names
    assert 'search_github_for_templates' in tool_names
    assert 'add_template' in tool_names
    assert 'list_templates' in tool_names


async def test_templates_list(mcp_client):
    result = await mcp_client.call_tool('list_templates', {})
    assert result.data.get('sample_tmplt') == 'minimal test dummy copier template'


@pytest.mark.asyncio
async def test_generate_project(mcp_client, tmp_template_dir):
    dst_path = os.path.join(tmp_template_dir, 'dist')

    res = await mcp_client.call_tool('start_project', {'template': 'sample_tmplt', 'destination': dst_path})
    assert res.data.get('next_question') == 'Name of project'

    res = await mcp_client.call_tool('set_next_parameter', {'response': 'proj_in_testing'})
    assert res.data.get('next_question') == 'Number of eels'
    
    res = await mcp_client.call_tool('set_next_parameter', {'response': '9'})
    assert res.data.get('next_question') == 'Estimated snack expenses to complete project'

    res = await mcp_client.call_tool('set_next_parameter', {'response': '10.02'})
    assert res.data.get('next_question') == 'Do you like hotdog?'

    res = await mcp_client.call_tool('set_next_parameter', {'response': 'no'})
    assert res.data.get('next_question') == 'A path'

    res = await mcp_client.call_tool('set_next_parameter', {'response': 'conf'})
    assert res.data.get('next_question') == 'Extra YAML data'

    res = await mcp_client.call_tool('set_next_parameter', {'response': 'x: uwu'})
    assert res.data.get('next_question') == 'Extra JSON data'

    res = await mcp_client.call_tool('set_next_parameter', {'response': '{"y": "UwU", "yy": "OwO"}'})
    assert res.data.get('next_question') == 'Who pays for the snacks?'

    res = await mcp_client.call_tool('set_next_parameter', {'response': 'jeff'})
    assert res.data.get('next_question') == 'Config file name'

    res = await mcp_client.call_tool('set_next_parameter', {'response': 'conf/settings.conf'})
    assert res.data.get('next_question') == 'Pick your lucky numbers'

    luckies = [1, 42, 1312]
    luckysum_path = os.path.join(dst_path, 'testing_project/luckysum.txt')
    new_name = 'testing_project'
    mcp_client.elicit_responses = [
        ['accept', {
            'project_name': new_name,
            'eels': '14',
            'hottodogu': 'yes',
        }],
        ['accept', {'value': ['project_name', 'eels', 'hottodogu']}],
    ]
    res = await mcp_client.call_tool('set_next_parameter', {'response': [str(n) for n in luckies]})
    assert res.content[0].text[:31] == 'Project created successfully at'
    assert os.path.isdir(os.path.join(dst_path, new_name))
    assert os.path.isfile(luckysum_path)
    with open(luckysum_path, 'r') as sumfile:
        assert int(sumfile.readline()) == sum(luckies)
