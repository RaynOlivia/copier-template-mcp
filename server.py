import asyncio
import logging
from os import path
from pydoc import locate
from typing import Literal
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
                fields[key] = (Literal[*params[key]['question']['choices']], Field(description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))
            case 'checkbox':
                fields[key] = (list[Literal[*params[key]['question']['choices']]], Field(description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))
            case 'confirm':
                fields[key] = (bool, Field(description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))
            case _:
                fields[key] = (str, Field(description = f'({params[key]['question'].get('message', '')})', default = params[key]['answer']))

    return create_model('TemplateParameters', **fields)


def get_next_question_output(question: dict, error: str|None = None) -> ToolResult:
    response_dict = {
        'next_question': question.get('message', question['name']).strip(),
        'instructions': 'Call the `set_next_parameter` tool to submit a value.'
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
    """Fill in a parameter for the template currently being generated and recieve the prompt for the next parameter.
    Use this tool only after starting the generation with the `start_project` tool.
    Returns the next template parameter to set by calling the `set_next_parameter` tool again.

    Args:
        response: Value for the next template parameter
    """
    generator.respond(response)
    log.debug('getting next question')
    question, error = generator.next_question()
    
    if question is not None:
        return get_next_question_output(question, error)

    else:
        log.debug('no more questions. starting elicitation')
        revise_response = await ctx.elicit(
            'Are the following parameters acceptable? If not, select the ones you wish to edit',
            response_type = [[f'{key} = {val["answer"]}' for key, val in generator.data.items()]]
        )
        if revise_response.action == 'accept' and len(revise_response.data) > 0:
            revise = [line.split(' = ', 1)[0] for line in revise_response.data]
            param_response = await ctx.elicit(
                'Please review project parameters',
                response_type = get_param_request_model(generator.data, revise)
            )
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
                return 'Project generation cancelled'
            # on decline procede with original params
            
        elif revise_response.action == 'cancel':
            return 'Project generation cancelled'
        
        log.debug('starting generator')
        coro = asyncio.to_thread(generator.generate)
        await coro
        return f'Project created successfully at {generator.dst_path}'


@mcp.tool
async def start_project(template: str, destination: str):
    """Start generating a new projec using a given copier template. Use when asked to create a project from a template.
    Returns the first template parameter to fill in using the `set_next_parameter` tool.
    
    Args:
        template: Name of the template to use.
        destination: Path to new project's directory.
    """
    global generator
    if generator is not None:
        generator.cancel()
    generator = copier_utils.Generator(template, destination)

    question, _ = generator.next_question()
    return get_next_question_output(question)


@mcp.tool
async def add_template(uri: str) -> str:
    """Add a copier template to the list of available templates and returns its parameters.
    Use this when given a git-repo or local path to use as template.

    Args:
        uri: Path to local or remote Git-repo of the template to be added.
    """

    try:
        name = path.splitext(path.basename(path.normpath(uri)))[0]
    except Exception:
        raise ToolError(f'Invalid URI: {uri}')

    try:
        copier_utils.clone_template(uri, name)
    except Exception:
        raise ToolError(f'Failed to clone template repo: {uri}')

    return f'Template is now available under the name `{name}`.'


@mcp.tool
async def list_templates() -> list[str]:
    """List available templates."""

    return copier_utils.get_templates()


if __name__ == '__main__':
    mcp.run()
