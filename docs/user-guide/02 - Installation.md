# Installation


## Requirements

- Python 3.14 or newer.
- A reachable Icinga installation (one or more of: Icinga 2 Core API, Icinga Web 2 with the Icinga DB Web module, Icinga Director).
- An MCP-capable client. Tested with [Claude Desktop](https://claude.ai/download) and [Claude Code](https://docs.claude.com/en/docs/claude-code).
- Optional: a time series database backend for historical perfdata. Default integration is InfluxDB; the TSDB layer is modular so other backends can be plugged in later.

The server itself runs anywhere Python 3.14 runs. It does not need to live on the Icinga master, but it does need network access to the Icinga REST APIs you point it at.


## Install from PyPI (planned)

Once a release is cut to PyPI:

```bash
pip install --user mcp-server-icinga
```

We recommend [pipx](https://pipx.pypa.io/) for an isolated install that does not leak into the system Python:

```bash
pipx install mcp-server-icinga
```


## Install from source

Until the first PyPI release, install directly from GitHub:

```bash
pip install --user git+https://github.com/Linuxfabrik/mcp-server-icinga.git
```

For local development:

```bash
git clone https://github.com/Linuxfabrik/mcp-server-icinga.git
cd mcp-server-icinga
python3.14 -m venv .venv
source .venv/bin/activate
pip install --editable '.'
```


## Verify the install

`mcp-server-icinga` is not a conventional CLI: it speaks JSON-RPC over stdin/stdout and takes no command-line arguments. A few quick checks confirm the install:

```bash
python -c 'from mcp_server_icinga import __version__; print(__version__)'   # prints the version
python -m mcp_server_icinga                                                 # same as the console script
mcp-server-icinga                                                           # exits: "no config file found ..."
```

Started without a configuration file the server exits immediately with a clear error pointing at the lookup order, which already confirms the binary runs.

To check that it actually answers a tool call over MCP - before wiring up any client - point it at an empty throwaway config and call `health_check` by hand:

```bash
touch /tmp/mcp-empty.yaml
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"cli","version":"1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{}}}' \
  | ICINGA_MCP_CONFIG=/tmp/mcp-empty.yaml mcp-server-icinga
```

Among the JSON-RPC replies is the `health_check` result: the server name and version, the config path, an empty `instances` map and the catalog status. That proves the install, the config lookup and the MCP stdio transport in one shot. (For what those three messages mean, see [How Tool Discovery Works](05 - How Tool Discovery Works.md).)

Next: [Configuration](03 - Configuration.md) wires the server to your Icinga, then [Quickstart with Claude](04 - Quickstart with Claude.md) connects it to Claude.
