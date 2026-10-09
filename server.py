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

import asyncio
import logging
from os import path, getcwd
from pydoc import locate
from typing import Literal
import requests
from fastmcp import FastMCP, Context
from mcp.types import SamplingMessage, TextContent
from fastmcp.tools.tool import ToolResult
from fastmcp.exceptions import ToolError
from pydantic import Field, create_model
import copier_utils

DEFAULT_PROJ_PATH = 'default_projects'

log = logging.Logger('MCP-server')
log.addHandler(logging.FileHandler('server.log', mode='a'))
log.setLevel(10)

mcp = FastMCP('copier-templates')
generator = None


def get_template_confirm_model(description: str):
    return create_model('TemplateConfirmation', description = (str, Field(
        description = f'Is the description ok like this?\n"{description}"',
        default = description
    )))


def get_python_type(copier_type: str):
    # copier types: bool, float, int, json, path, str, yaml
    if copier_type in ('json', 'path', 'yaml', None):
        return str
    else:
        return locate(copier_type) or str


def get_param_request_model(params: dict, to_revise: list):
    fields = {}
    log.debug(f'revising params: {to_revise}')
    for key in to_revise:
        match params[key]['question']['type']:
            case 'select':
                log.debug(f'select param: {key}')
                fields[key] = (Literal[*params[key]['question']['choices']], Field(title = key, description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))
            case 'checkbox':
                log.debug(f'checkbox param: {key}')
                fields[key] = (list[Literal[*params[key]['question']['choices']]], Field(title = key, description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))
            case 'confirm':
                log.debug(f'confirm param: {key}')
                fields[key] = (bool, Field(title = key, description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))
            case _:
                log.debug(f'generic param: {key}')
                fields[key] = (str, Field(title = key, description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))

    return create_model('TemplateParameters', **fields)


def get_next_question_output(question: dict, error: str|None = None) -> ToolResult:
    log.debug('question getting output')
    response_dict = {
        'next_question': question.get('message', question['name']).strip(),
        'instructions': 'Call the `set_next_parameter` tool to submit an answer'
    }
    if 'choices' in question:
        response_dict['options'] = [c.value or c.title for c in question['choices'] if not c.disabled]
        log.debug(f'question getting output {response_dict}')
        if question['type'] == 'select':
            response_dict['instructions'] += ' Respond with one of the options'
        else:
            response_dict['instructions'] += ' Respond with a list of selected options'
    if error is not None:
        response_dict['next_question'] = f'ERROR: {error}. Try again: {response_dict['next_question']}'

    return ToolResult(
        structured_content = response_dict
    )


async def finish_generation(ctx: Context):
    log.debug('no more questions. starting elicitation')
    update = generator.update
    verb = 'update' if update else 'generation'

    revise_response = await ctx.elicit(
        message =   'Template parameters have changed. Would you like to review new parameters before update?' if update else \
                    'Would you like to review the template parameters before generation?',
        response_title = 'Revision',
        response_description = 'Select the parameter values you wish to revise (parameter names in brackets)',
        response_type = [{str(key): {'title': str(val["answer"])} for key, val in generator.data.items()}]
    )
    log.debug('pre post elic')
    if revise_response.action == 'accept' and len(revise_response.data) > 0:
        revise = [line for line in revise_response.data]
        log.debug('pre elic')
        param_response = await ctx.elicit(
            message = 'Please review the selected parameters',
            response_type = get_param_request_model(generator.data, revise)
        )
        log.debug('post elic')
        if param_response.action == 'accept':
            for key in revise:
                new_answer = getattr(param_response.data, key)
                validator = generator.data[key]['question'].get('validate', lambda _: True)
                out_filter = generator.data[key]['question'].get('filter', lambda x: x)
                verdict = validator(new_answer)
                if verdict == True:
                    generator.data[key]['answer'] = out_filter(new_answer)
                else:
                    return f'Project {verb} cancelled'  # TODO: re-elicit!
        elif param_response.action == 'cancel':
            return f'Project {verb} cancelled by user'
        # on decline procede with original params
        
    elif revise_response.action == 'cancel':
        return f'Project {verb} cancelled by user'
    # on decline procede with generation without changes
    
    log.debug(f'starting {verb}')
    coro = asyncio.to_thread(generator.generate)
    await coro
    if update:
        conflicts = generator.get_merge_conflicts()
        if len(conflicts) < 1:
            return 'Project updated successfully!'
        return ToolResult(
            structured_content = {
                'merge_conflicts': conflicts,
                'instructions': f'Project updated! Now resolve the merge conflicts in these files within {generator.dst_path!r}.' \
                                 'Consult README and commit history for context and attempt to preserve the intent behind both changes.' \
                                 'Prefer current changes over incoming if conflict is unresolvable. Ask user for input if necessary'
            }
        )
    return f'Project created successfully at {generator.dst_path}'


async def start_new_generator(ctx: Context, update: bool, destination: str, template: str = ''):
    global generator
    destination = path.expanduser(path.expandvars(path.join(getcwd(), DEFAULT_PROJ_PATH, destination)))
    if generator is not None:
        generator.cancel()

    generator = copier_utils.Generator(template, destination, update)
    question, _ = generator.next_question()
    if question is None:
        return await finish_generation(ctx)
    return get_next_question_output(question)



@mcp.tool
async def set_next_parameter(ctx: Context, response: str|list[str]):
    """Fill in a parameter for the template currently being generated and receive the prompt for the next parameter
    Use this tool only after starting the generation with the `start_project` tool

    Args:
        response: Value for the next template parameter

    Returns:
        Next template parameter to set and instructions on what to do next
    """

    log.debug(f'response: {response}')
    generator.respond(response)
    log.debug('getting next question')
    question, error = generator.next_question()
    
    if question is not None:
        return get_next_question_output(question, error)

    else:
        return await finish_generation(ctx)


@mcp.tool
async def start_project(ctx: Context, template: str, destination: str):
    """Start generating a new projec using a given copier template
    
    Args:
        template: Name of the template to use
        destination: Absolute path to new project's directory

    Returns:
        First template parameter to fill in using the `set_next_parameter` tool and instructions on what to do next
    """
    try:
        return await start_new_generator(ctx, False, destination, template)
    except Exception as e:
        raise ToolError(str(e))


@mcp.tool
async def update_project(ctx: Context, project_path: str):
    """Update a template-generated project if template has changed since generation
    Might require new parameters to be set using `set_next_parameter` tool

    Args:
        project_path: Absolute path to project directory

    Returns:
        Instructions on what to do next
    """
    try:
        return await start_new_generator(ctx, True, project_path)
    except Exception as e:
        raise ToolError(str(e))


@mcp.tool
async def search_github_for_templates(query: str) -> list[dict[str, str]]:
    """Search Github for copier templates to add to the list of templates
    Use this when no fitting template for a new project exists to find and add a template instead of writing a project from scratch

    Args:
        query: Github search query. Ideally less than 3 keywords

    Returns:
        List of at most 200 search results
    """
    url = f'https://api.github.com/search/repositories?q=copier+template+{requests.utils.quote(query.strip())}'
    response = requests.get(url, timeout = 20)
    response.raise_for_status()
    results = response.json().get('items', [])
    return [{
        'name': repo.get('name', ''),
        'url': repo.get('clone_url', ''),
        'github-description': repo.get('description', '').strip()
    } for repo in results[:200]]


@mcp.tool
async def add_template(ctx: Context, uri: str, description: str) -> str:
    """Add a copier template to the list of available templates

    Args:
        uri: Path to local directory or remote Git-repo of the template to be added
        description: A short text explaining the template and when it should be used (max 500 char)
    """
    if len(description) > 500:
        raise ToolError(f'Description too long. Max 500 char')

    try:
        name = path.splitext(path.basename(path.normpath(uri)))[0]
    except Exception:
        raise ToolError(f'Invalid URI: {uri}')

    
    confirm_response = await ctx.elicit(
        message = f'Add {name!r} to copier template list? - URL: {uri}',
        response_type = get_template_confirm_model(description)
    )
    if confirm_response.action == 'accept':
        try:
            copier_utils.add_template(name, uri, confirm_response.data.description or description)
        except Exception:
            raise ToolError(f'Failed to add template')

        return f'Template is now available under the name `{name}`'
    else:
        return 'Template rejected by user'


@mcp.tool
async def list_templates() -> dict[str, str]:
    """List available templates with descriptions
    Use this when asked to create a new project and if a template matches the desired project specs use it with the `start_project` tool instead of coding from scratch
    """
    yam = copier_utils.get_templates()
    res = {name: props.get('description') or '' for name, props in yam.items()}
    log.debug(yam)
    log.debug(res)
    return res


if __name__ == '__main__':
    mcp.run()
