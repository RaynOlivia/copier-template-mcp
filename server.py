import asyncio
import logging
from os import path
from pydoc import locate
from typing import Literal
import requests
from fastmcp import FastMCP, Context
from mcp.types import SamplingMessage, TextContent
from fastmcp.tools.tool import ToolResult
from fastmcp.exceptions import ToolError
from pydantic import Field, create_model
import copier_utils


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
    response_dict = {
        'next_question': question.get('message', question['name']).strip(),
        'instructions': 'Call the `set_next_parameter` tool to submit a value'
    }
    if 'choices' in question:
        response_dict['options'] = question.choices
        if question['type'] == 'select':
            response_dict['instructions'] += ' Respond with one of the options'
        else:
            response_dict['instructions'] += ' Respond with a list of selected options'
    if error is not None:
        response_dict['next_question'] = f'ERROR: {error}. Try again: {response_dict['next_question']}'

    return ToolResult(
        structured_content = response_dict
    )


@mcp.tool
async def set_next_parameter(ctx: Context, response: str|list[str]):
    """Fill in a parameter for the template currently being generated and receive the prompt for the next parameter
    Use this tool only after starting the generation with the `start_project` tool

    Args:
        response: Value for the next template parameter

    Returns:
        Next template parameter to set by calling the `set_next_parameter` tool again
    """
    generator.respond(response)
    log.debug('getting next question')
    question, error = generator.next_question()
    
    if question is not None:
        return get_next_question_output(question, error)

    else:
        log.debug('no more questions. starting elicitation')
        revise_response = await ctx.elicit(
            message = 'Would you like to review the template parameters before generation?',
            response_title = 'Revision',
            response_description = 'Select the parameter values you wish to revise (parameter names in brackets)',
            response_type = [{str(key): {'title': str(val["answer"])} for key, val in generator.data.items()}]
        )
        log.debug(f'pre post elic: {"; ".join(revise_response.data)}')
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
                        return 'Project generation cancelled'  # TODO: re-elicit!
            elif param_response.action == 'cancel':
                return 'Project generation cancelled by user'
            # on decline procede with original params
            
        elif revise_response.action == 'cancel':
            return 'Project generation cancelled by user'
        # on decline procede with generation without changes
        
        log.debug('starting generator')
        coro = asyncio.to_thread(generator.generate)
        await coro
        return f'Project created successfully at {generator.dst_path}'


@mcp.tool
async def start_project(template: str, destination: str):
    """Start generating a new projec using a given copier template
    
    Args:
        template: Name of the template to use
        destination: Path to new project's directory

    Returns:
        First template parameter to fill in using the `set_next_parameter` tool
    """
    global generator
    if generator is not None:
        generator.cancel()
    generator = copier_utils.Generator(template, destination)

    question, _ = generator.next_question()
    return get_next_question_output(question)


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
    response = requests.get(url)
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
