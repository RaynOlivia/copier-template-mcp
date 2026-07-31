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


def get_sampling_model(question: dict):
    fields = {'reasoning': (str, Field(description = 'a thinking process'))}
    match question['type']:
        case 'select':
            fields['selection'] = (int, Field(description = 'number of chosen option'))
        case 'checkbox':
            fields['selections'] = (list[int], Field(description = 'list of numbers of chosen options'))
        case 'confirm':
            fields['response'] = (bool, Field(description = 'yes (True) or no (False)'))
        case _:
            fields['response'] = (str, Field(description = 'final parameter value'))

    return create_model('SamplingResponse', **fields)


@mcp.tool
async def generate_project(ctx: Context, template: str, destination: str, description: str) -> str:
    """Generate a new project given a copier template name and a project description. Use when asked to create a project from a template
    
    Args:
        template: Name of the template to use.
        destination: Path to new project's directory.
        description: Freeform summary of the project's goals and design criteria.
    """
    
    if not template in copier_utils.get_templates():
        raise ToolError(f'Template not found: {template}')

    sampling_system_prompt = (
        f'You are generating a software project using a template: {description}\n'
        'Based on this description fill in the following template parameters. \n'
        'Respond only with the final parameter value'
    )
    sampling_messages = []
    sampling_answers = {'PROJECT_PATH': {
        'question': {
            'type': 'path',
            'name': 'PROJECT_PATH',
            'message': 'Path to new project. Will be overwritten if exists!'
        },
        'answer': destination
    }}

    log.debug(f'STARTING COPIER')
    generator = copier_utils.Generator(template, destination)
    
    question, repeat = generator.next_question()
    log.debug(f'queshn: {question['name']}')
    while question is not None:
        if repeat is None:
            next_message = question.get('message', question['name']).strip()
        else:
            next_message = repeat + '. Try again!'

        if 'choices' in question:
            if question['type'] == 'select':
                next_message += '\nSelect one of the following options:\n'
            else:
                next_message += '\nSelect any number of the following options:\n'
            next_message += '\n'.join([f'  {i}) {c}' for i, c in enumerate(question['choices'])])

        log.debug(f'QUESTION: {next_message}')

        sampling_messages.append(SamplingMessage(
            role = 'user',
            content = TextContent(type = 'text', text = next_message)
        ))
        sampling_response = await ctx.sample(
            system_prompt = sampling_system_prompt,
            messages = sampling_messages,
            result_type = get_sampling_model(question)
        )
        sampling_messages = sampling_response.history

        log.debug(f'ANSWER!: {sampling_response.result}')

        match question['type']:
            case 'select':
                reply = question['choices'][sampling_response.result.selection]
            case 'checkbox':
                reply = [question['choices'][i] for i in sampling_response.result.selections]
            case _:
                reply = sampling_response.result.response
        
        generator.respond(reply)
        question, repeat = generator.next_question()
        if repeat is None:
            sampling_answers[question['name']] = {'question': question, 'answer': reply}

    response = await ctx.elicit(
        'Are the following parameters acceptable? If not, select the ones you wish to edit',
        response_type = [[f'{key} = {val["answer"]}' for key, val in sampling_answers.items()]]
    )
    if response.action == 'accept' and len(response.data) > 0:
        revise = [line.split(' = ', 1)[0] for line in response.data]
        param_response = await ctx.elicit(
            'Please review project parameters',
            response_type = get_param_request_model(sampling_answers, revise)
        )
        if param_response.action == 'accept':
            for key in revise:
                new_answer = getattr(param_response.data, key)
                validator = sampling_answers[key]['question'].get('validate', lambda _: True)
                out_filter = sampling_answers[key]['question'].get('filter', lambda x: x)
                verdict = validator(new_answer)
                if verdict == True:
                    sampling_answers[key]['answer'] = out_filter(new_answer)
                else:
                    return 'Project generation cancelled'  # TODO: re-elicit!
        elif response.action == 'cancel':
            return 'Project generation cancelled'
        # on decline procede with original params
        
    elif response.action == 'cancel':
        return 'Project generation cancelled'
    
    coro = asyncio.to_thread(copier_utils.generate, template, response.data.PROJECT_PATH, {key: val['answer'] for key, val in sampling_answers.items()})
    await coro
    return f'Project created at {response.data.PROJECT_PATH}'



    # def question_handler(questions, answers):
    #     nonlocal sampling_messages
    #     nonlocal sampling_answers

    #     question = questions[0]
    #     if not question['when']('UwU'):
    #         return {}

    #     # log.debug('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
    #     # log.debug(type(question.get('message')))
    #     # log.debug(repr(question.get('message')))

    #     sampling_messages.append(SamplingMessage(
    #         role = 'user',
    #         content = TextContent(type = 'text', text = question.get('message', question['name']))
    #     ))
    #     response = ctx.sample(
    #         system_prompt = sampling_system_prompt,
    #         messages = sampling_messages
    #     )
    #     sampling_messages = response.history

    #     validator = question.get('validate')
    #     while callable(validator):
    #         verdict = validator(response.text)
    #         if verdict == True:
    #             break
    #         else:
    #             sampling_messages.append(SamplingMessage(
    #                 role = 'user',
    #                 content = TextContent(type = 'text', content = f'{verdict}. Try again.')
    #             ))
    #             response = ctx.sample(
    #                 system_prompt = sampling_system_prompt,
    #                 messages = sampling_messages
    #             )
    #             sampling_messages = response.history

    #     out_filter = question.get('filter', lambda x: x)
    #     answer = out_filter(response.text)
    #     sampling_answers[question['name']] = {'question': question, 'answer': answer}
    #     return {question['name']: answer}



@mcp.tool
async def add_template(uri: str) -> ToolResult:
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
    
    params = copier_utils.get_params(name)
    return ToolResult(
        content = f'Template is now available under the name `{name}`.\n'\
                  f'It has {len(params)} parameters: `{"`, `".join(params.keys())}`.',
        structured_content = {'parameters': params}
    )


@mcp.tool
async def list_templates() -> list[str]:
    """List available templates."""

    return copier_utils.get_templates()


if __name__ == '__main__':
    mcp.run()
