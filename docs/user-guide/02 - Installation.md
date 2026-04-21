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

The package exposes both a console script and a runnable module:

```bash
mcp-server-icinga --help        # short usage banner (no arguments accepted)
python -m mcp_server_icinga     # equivalent
python -c 'from mcp_server_icinga import __version__; print(__version__)'
```

Without a configuration file the server exits with a clear error pointing at the lookup order. That is the expected behaviour at this stage; head over to [Configuration](03 - Configuration.md) next.
