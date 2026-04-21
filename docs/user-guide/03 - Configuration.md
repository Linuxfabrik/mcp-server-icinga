# Configuration

`mcp-server-icinga` is configured through a single YAML file. Secrets do not live in the YAML; they are referenced via the `!env VAR_NAME` tag and injected as environment variables by the MCP client when it spawns the server.


## Lookup order

The server checks for a configuration file in this order and uses the first match:

1. The path in the `ICINGA_MCP_CONFIG` environment variable.
2. `$XDG_CONFIG_HOME/mcp-server-icinga/config.yaml` (default: `~/.config/mcp-server-icinga/config.yaml`).
3. `/etc/mcp-server-icinga/config.yaml`.

For local testing the user-specific path is the most convenient. For systemd-managed deployments the system path is the natural choice. Use `ICINGA_MCP_CONFIG` to override both, for example to point at a tenant-specific file.


## Minimal configuration

An empty file is valid. The server will start, but no backend is configured and only the `health_check` tool will be registered. Useful as a "is the wiring correct" smoke test:

```bash
mkdir --parents ~/.config/mcp-server-icinga
touch ~/.config/mcp-server-icinga/config.yaml
```


## Full example

A full configuration covering all backends. The annotated example also ships at `examples/config.example.yaml` in the source tree.

```yaml
icinga2_core:
  url: 'https://icinga2.example.com:5665'
  username: 'mcp-readonly'
  password: !env ICINGA2_CORE_PASSWORD
  verify_tls: true
  # ca_bundle: '/etc/pki/tls/certs/ca.pem'
  timeout: 8

  # Optional second credential pair for write operations (acknowledge,
  # schedule_downtime, reschedule_check, ...). Leave commented out to keep
  # the server in read-only mode for this backend.
  # write_username: 'mcp-write'
  # write_password: !env ICINGA2_CORE_WRITE_PASSWORD

icinga_web:
  url: 'https://icingaweb.example.com'
  username: 'mcp'
  password: !env ICINGA_WEB_PASSWORD

icinga_director:
  url: 'https://icingaweb.example.com/director'
  username: 'mcp-director'
  password: !env ICINGA_DIRECTOR_PASSWORD

tsdb:
  type: 'influxdb'
  url: 'http://influxdb.example.com:8086'
  org: 'linuxfabrik'
  bucket: 'icinga'
  token: !env INFLUXDB_TOKEN

monitoring_plugins:
  catalog_path: '/opt/linuxfabrik/monitoring-plugins/check-plugins'
```


## Field reference

Every section is independently optional. Tools whose backend is missing do not get registered. The schema is enforced at startup; unknown keys are rejected with a clear error message.

### `icinga2_core`

| Field             | Type     | Required | Default | Description |
|-------------------|----------|----------|---------|-------------|
| `url`             | URL      | yes      | -       | Base URL of the Icinga 2 Core REST API, typically port 5665. |
| `username`        | string   | yes      | -       | Read-capable API user. |
| `password`        | secret   | yes      | -       | Read-capable user's password. Use `!env` to reference an environment variable. |
| `verify_tls`      | bool     | no       | `true`  | Verify the server certificate. Set to `false` for self-signed certs in test environments. |
| `ca_bundle`       | path     | no       | -       | Custom CA bundle file used for certificate verification. |
| `timeout`         | int      | no       | `8`     | Network timeout in seconds. |
| `write_username`  | string   | no       | -       | Optional second user with write permissions. When unset, write tools are not registered. |
| `write_password`  | secret   | no       | -       | Required if `write_username` is set. |

### `icinga_web`

Same fields as `icinga2_core`, minus the write-credential pair. Points at an Icinga Web 2 installation that has the Icinga DB Web module enabled.

### `icinga_director`

Same fields as `icinga_web`. Often the same Icinga Web instance with the Director module enabled.

### `tsdb`

Modular. Currently only `type: 'influxdb'` is implemented.

| Field         | Type     | Required | Default | Description |
|---------------|----------|----------|---------|-------------|
| `type`        | string   | yes      | -       | `'influxdb'` (other backends to follow). |
| `url`         | URL      | yes      | -       | InfluxDB 2.x base URL. |
| `org`         | string   | yes      | -       | InfluxDB organisation. |
| `bucket`      | string   | yes      | -       | Bucket holding the Icinga perfdata. |
| `token`       | secret   | yes      | -       | API token. |
| `verify_tls`  | bool     | no       | `true`  | Verify the server certificate. |
| `ca_bundle`   | path     | no       | -       | Custom CA bundle file. |
| `timeout`     | int      | no       | `8`     | Network timeout in seconds. |

### `monitoring_plugins`

| Field          | Type | Required | Default | Description |
|----------------|------|----------|---------|-------------|
| `catalog_path` | path | no       | -       | Local checkout of the `monitoring-plugins` repository's `check-plugins/` directory. When unset, the server falls back to the JSON snapshot bundled with the package. |


## Secrets

Never put plain-text passwords or tokens into the YAML file. Use the `!env` tag to refer to an environment variable; the MCP client (Claude Desktop, Claude Code, MCPO, ...) is expected to inject these into the server process when it starts:

```yaml
password: !env ICINGA2_CORE_PASSWORD
```

If the environment variable is missing at startup, the server fails fast with a clear error mentioning the variable name. This makes credential issues obvious in the MCP client log.

For credential management itself, use whatever mechanism your operating environment already provides:

- A systemd unit with `EnvironmentFile=/etc/mcp-server-icinga/secrets.env`.
- An MCP client wrapper that pulls secrets from a vault and injects them into the spawned process.
- A direct entry in the MCP client's `env` map - convenient for local dev, less so for production.


## Where to go next

- [Quickstart with Claude](04 - Quickstart with Claude.md): wire the server into Claude Desktop or Claude Code and run the first tool.
