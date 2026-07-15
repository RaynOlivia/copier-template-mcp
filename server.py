import copier_utils
import asyncio
from os import path
from mcp.shared.exceptions import McpError
from mcp.server import Server
import mcp.server.stdio as mcpio
import mcp.types as types
import json

app = Server('copier-templates')


@app.list_tools()
async def list_tools():
    '''Return the list of available tools.'''

    return [
        types.Tool(
            name='generate-project',
            description='Generate a new project given a template and a set of parameters',
            inputSchema={
                'type': 'object',
                'properties': {
                    'template': {
                        'type': 'string',
                        'description': 'Name of the template to use',
                    },
                    'destination': {
                        'type': 'string',
                        'description': 'Path to new project\'s directory',
                    },
                    'params': {
                        'type': 'object',
                        'description': 'Values for each parameter required by the template',
                    }
                },
                'required': ['template', 'destination', 'params'],
            },
        ),
        types.Tool(
            name='add-template',
            description='Add a copier template to the list of available templates',
            inputSchema={
                'type': 'object',
                'properties': {
                    'uri': {
                        'type': 'string',
                        'description': 'Uri to local or remote Git-repo of the template to be added',
                    },
                },
                'required': ['uri'],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    '''Handle tool invocations.'''
    if name == 'add-template':
        uri = str(arguments.get('uri'))
        name = path.splitext(path.basename(path.normpath(uri)))[0]
        try:
            copier_utils.clone_template(uri, name)
        except Exception as e:
            raise McpError(types.ErrorData(
                code = types.INTERNAL_ERROR,
                message = f'Failed to clone template {uri}:\n{e}\n',
            ))
        return [types.TextContent(type='text', text=f'Template {uri} is now available under the name {name}')]

    if name == 'generate-project':
        template_name = arguments.get('template')
        destination = arguments.get('destination')
        parameters = arguments.get('params')
        if not template_name in copier_utils.get_templates():
            raise McpError(types.ErrorData(
                code = types.INVALID_PARAMS,
                message = f'Template does not exist: {template_name}',
            ))
        if not path.isdir(destination):
            raise McpError(types.ErrorData(
                code = types.INVALID_PARAMS,
                message = f'Destination directory does not exist: {destination}',
            ))
        if not sorted(list(parameters.keys())) == sorted(list(copier_utils.get_params(template_name).keys())):
            raise McpError(types.ErrorData(
                code = types.INVALID_PARAMS,
                message = f'Parameter names don\'t match the ones required by template {template_name}',
            ))
        try:
            copier_utils.generate(template_name, destination, parameters)
        except Exception:
            raise McpError(types.ErrorData(
                code = types.INTERNAL_ERROR,
                message = 'Project generation failed',
            ))
        return [types.TextContent(type='text', text=f'Project generated at {destination}')]
        
    raise McpError(types.ErrorData(
        code = types.INVALID_PARAMS,
        message = f'Unknown tool: {name}',
    ))


@app.list_resources()
async def list_resources():
    '''Return the list of available resources.'''

    return [
        types.Resource(
            uri = f'params://{name}',
            name = name,
            description = f'Parameters required by template {name}',
        )
        for name in copier_utils.get_templates()
    ]


@app.read_resource()
async def read_resource(uri: str):
    '''Handle resource reads.'''

    try:
        name = str(uri).split('://')[1].strip('/')
        assert name in copier_utils.get_templates()
    except Exception as e:
        raise McpError(types.ErrorData(
            code = types.INVALID_PARAMS,
            message = f'Resource not found: {uri}\n{e}\n',
        ))
    else:
        return json.dumps(copier_utils.get_params(name), indent=2)


async def main():
    async with mcpio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == '__main__':
    asyncio.run(main())
