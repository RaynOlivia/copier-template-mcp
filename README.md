# CopierMCP

An mcp server to allow AI agents to use Copier-templates when generating new projects. This reduces token use and makes agent-created projects less error-prone and more reproducible.

CopierMCP is developed to work with the [Pi harness](https://pi.dev/) using [Pi MCP Adapter](https://pi.dev/packages/pi-mcp-adapter) but can work with any MCP-compatible agent. 

## Installation


<!-- ## Usage
1. Ask agent to create a new project
2. Agent will search the local template list for an applicable template
3. If no existing template fits, agent will search github for an applicable copier template and ask user for confirmation before adding it
4. After choosing a template agent will make multiple tool calls to fill out the parameters of the template
5. Agent will present template parameters to user for editing through elicitation before generating the project -->

## Features
- Project creation from templates
- Project updating after changes to template
- Github search for new templates
- Locally maintained template list
- User confirmations for project parameters and template list changes