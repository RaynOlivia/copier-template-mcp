from os import path
from fastmcp import FastMCP, Context
from fastmcp.tools.tool import ToolResult
from fastmcp.exceptions import ToolError
from pydantic import Field, create_model
from typing import Annotated
from pydoc import locate
import copier_utils
import asyncio

mcp = FastMCP('copier-templates')


def get_param_request_model(destination: str, params: dict, schema: dict):
    fields = {'PROJECT_PATH': (str, Field(
        description = f'- Contents will be overriden if not empty! - def: {destination}',
        default = destination
    ))}
    for key, value in schema.items():
        # copier types: bool, float, int, json, path, str, yaml
        ctype = value.get('type')
        if ctype is None:
            ctype = 'str'
            ptype = str
        elif ctype in ('json', 'path', 'yaml'):
            ptype = str
        else:
            ptype = locate(ctype)

        description = f'- {value["description"]} ({ctype}) - '
        entry = params.get(key)
        if entry is None or entry == '':
            entry = None
            description += 'REQUIRED'
        else:
            description += f'def: {entry}'

        fields[key] = (ptype, Field(description = description, default = entry))

    return create_model('TemplateParameters', **fields)


@mcp.tool(timeout = 1800.0)
async def generate_project(ctx: Context, template: str, destination: str, params: dict[str, str]) -> str:
    """Generate a new project given a template and a set of parameters.
    
    Args:
        template: Name of the template to use.
        destination: Path to new project's directory.
        params: Values for each parameter required by the template. Parameter names are provided by get_template_params.
    """
    
    if not template in copier_utils.get_templates():
        raise ToolError(f'Template not found: {template}')
    schema = copier_utils.get_params(template)

    response = await ctx.elicit(
        message = 'Please confirm project parameters',
        response_type = get_param_request_model(destination, params, schema)
    )
    match response.action:
        case 'accept':
            final_params = {key: getattr(response.data, key) for key in schema}
            copier_utils.generate(template, response.data.PROJECT_PATH, final_params)
            return f'Project created at {response.data.PROJECT_PATH}'

        case 'decline':
            return 'Project parameters not accepted'
        case 'cancel':
            return 'Project generation cancelled'


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


@mcp.tool
async def get_template_params(template: str) -> ToolResult:
    """Get list of parameters required by a given template with names, types and descriptions.
    
    Args:
        template: Name of template to inspect.
    """

    params = copier_utils.get_params(template)
    return ToolResult(
        content = f'{template} has {len(params)} parameters: `{"`, `".join(params.keys())}`.',
        structured_content = {'parameters': params}
    )


if __name__ == '__main__':
    mcp.run()
