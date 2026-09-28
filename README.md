# CopierMCP

An MCP server to allow AI agents to use Copier-templates when generating new projects. It aims to reduce the ammount of vibe-code in vibe-coded projects thereby improving reproducibility and reducing token-use

CopierMCP is developed to work with the [Pi harness](https://pi.dev/) using [Pi MCP Adapter](https://pi.dev/packages/pi-mcp-adapter) but can work with any MCP-compatible agent. 

## Installation
Instructions apply to Pi. Adapt for your agent accordingly

1. clone this repo and install python dependencies in a venv:
``` bash
git clone https://github.com/RaynOlivia/copier-template-mcp.git
cd copier-template-mcp
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
2. add the following to the `mcpServers` block in `~/.pi/agent/mcp.json`:
``` json
"copier-templates": {
    "command": "venv/bin/python3",
    "args": [ "server.py" ],
    "cwd": "<INSTALL_PATH>",
    "directTools": true,
    "elicitation": true,
    "requestTimeoutMs": 1800000
}
```
replace `<INSTALL_PATH>` with where you cloned the CopierMCP to

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


<!-- ## Template Management -->

## License
Licensed under the GNU General Public License, version 3: ([LICENSE](LICENSE) or
<https://www.gnu.org/licenses/gpl-3.0.html>)
