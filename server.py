from os import path
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from fastmcp.exceptions import ToolError
import copier_utils
import asyncio
import json

mcp = FastMCP('copier-templates')


@mcp.tool
async def generate_project(template: str, destination: str, params: dict[str, str]) -> str:
    """Generate a new project given a template and a set of parameters.
    
    Args:
        template: Name of the template to use.
        destination: Path to new project's directory.
        params: Values for each parameter required by the template. Parameter names are provided by get_template_params.
    """
    
    if not template in copier_utils.get_templates():
        raise ToolError(f'Template does not exist: {template}')
    if not path.isdir(destination):
        raise ToolError(f'Destination directory does not exist: {destination}')
    if not sorted(list(params.keys())) == sorted(list(copier_utils.get_params(template).keys())):
        raise ToolError(f'Parameter names don\'t match the ones required by template {template}')
    
    copier_utils.generate(template, destination, params)
    return f'Project generated at {destination}'


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
                  f'It has {len(params)} parameters: `{"`, `".join([ p["name"] for p in params ])}`.',
        structured_content = {'params': params}
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
        content = f'{template} has {len(params)} parameters: `{"`, `".join([ p["name"] for p in params ])}`.',
        structured_content = {'params': params}
    )


if __name__ == '__main__':
    mcp.run()
