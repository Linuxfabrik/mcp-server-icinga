# Configuration

`mcp-server-icinga` is configured through a single YAML file. The file describes one or more Icinga deployments ("instances") plus the global Linuxfabrik monitoring-plugins catalog. Secrets do not live in the YAML; they are resolved at load time from environment variables (`!env`) or from files on disk (`!file`).


## Lookup order

The server checks for a configuration file in this order and uses the first match:

1. The path in the `ICINGA_MCP_CONFIG` environment variable.
2. `$XDG_CONFIG_HOME/mcp-server-icinga/config.yaml` (default: `~/.config/mcp-server-icinga/config.yaml`).
3. `/etc/mcp-server-icinga/config.yaml`.

For local testing the user-specific path is the most convenient. For systemd-managed deployments the system path is the natural choice. Use `ICINGA_MCP_CONFIG` to override both, for example to point at a tenant-specific file.


## The shape: instances + globals

Two top-level sections:

- `instances`: a map from instance name (an arbitrary identifier like `prod-zh`, `staging` or `customer-acme`) to a per-deployment configuration with up to four backends (`icinga2_core`, `icinga_web`, `icinga_director`, `tsdb`).
- `monitoring_plugins`: global, applies across every instance.

Both sections are optional. An empty file (or a file with `instances: {}`) is valid: the server starts and only registers the global tools (`health_check`, plus the catalog tools when `monitoring_plugins.catalog_path` is set).


## Minimal configurations

**Smoke test.** No instance, no catalog, only `health_check` works:

```bash
mkdir --parents ~/.config/mcp-server-icinga
touch ~/.config/mcp-server-icinga/config.yaml
```

**Single Icinga 2 Core, read-only:**

```yaml
instances:
  prod:
    icinga2_core:
      url: 'https://icinga2.example.com:5665'
      username: 'mcp-readonly'
      password: !env ICINGA2_PROD_PASSWORD
```

**Multi-tenant, mixed secret sources:**

```yaml
instances:
  prod-zh:
    icinga2_core:
      url: 'https://icinga2-prod-zh.example.com:5665'
      username: 'mcp-readonly'
      password: !file /run/credentials/mcp-server-icinga/icinga2-prod-zh-password

  prod-fr:
    icinga2_core:
      url: 'https://icinga2-prod-fr.example.com:5665'
      username: 'mcp-readonly'
      password: !env ICINGA2_PROD_FR_PASSWORD

  staging:
    icinga2_core:
      url: 'https://icinga2-stg.example.com:5665'
      username: 'mcp-readonly'
      password: !env ICINGA2_STG_PASSWORD
      verify_tls: false

monitoring_plugins:
  catalog_path: '/opt/linuxfabrik/monitoring-plugins/check-plugins'
```

The annotated full example with all backends per instance lives at `examples/config.example.yaml` in the source tree.


## Field reference

### `instances.<name>`

The key under `instances` is the instance name. Tools that target a specific instance accept the name as a parameter. Pick a stable identifier you can remember in the chat: a site code, a customer name, an environment label.

Each instance contains zero to four of the following backend sections. They are all independently optional; a tool whose backend is missing on the targeted instance refuses with a clear error.

#### `instances.<name>.icinga2_core`

| Field             | Type     | Required | Default | Description |
|-------------------|----------|----------|---------|-------------|
| `url`             | URL      | yes      | -       | Base URL of the Icinga 2 Core REST API, typically port 5665. |
| `username`        | string   | yes      | -       | Read-capable API user. |
| `password`        | secret   | yes      | -       | Read-capable user's password. Use `!env` or `!file`. |
| `verify_tls`      | bool     | no       | `true`  | Verify the server certificate. Set to `false` for self-signed certs in test environments. |
| `ca_bundle`       | path     | no       | -       | Custom CA bundle file used for certificate verification. |
| `timeout`         | int      | no       | `8`     | Network timeout in seconds. |
| `write_username`  | string   | no       | -       | Optional second user with write permissions. When unset, write tools are not registered for this instance. |
| `write_password`  | secret   | no       | -       | Required when `write_username` is set. |

#### `instances.<name>.icinga_web`

Same fields as `icinga2_core`, minus the write-credential pair. Points at an Icinga Web 2 installation that has the Icinga DB Web module enabled.

#### `instances.<name>.icinga_director`

Same fields as `icinga_web`. Often the same Icinga Web instance with the Director module enabled.

#### `instances.<name>.tsdb`

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

Global. Same plugin catalog applies across every instance.

| Field          | Type | Required | Default | Description |
|----------------|------|----------|---------|-------------|
| `catalog_path` | path | no       | -       | Local checkout of the `monitoring-plugins` repository's `check-plugins/` directory. When unset, the server falls back to the JSON snapshot bundled with the package. |


## Secrets

Never put plain-text passwords or tokens into the YAML file. Two custom YAML tags are available:

### `!env VAR_NAME`

Reads the value from an environment variable. The MCP client (Claude Desktop, Claude Code, MCPO, ...) is expected to inject these into the spawned server process:

```yaml
password: !env ICINGA2_PROD_ZH_PASSWORD
```

If the environment variable is missing at startup, the server fails fast with a clear error mentioning the variable name. This makes credential issues obvious in the MCP client log.

### `!file /path/to/secret`

Reads the value from a file on disk. The trailing newline is stripped (so `echo "secret" > /run/credentials/...` works). Useful when:

- The secret comes from systemd's `LoadCredential=` mechanism (`/run/credentials/<unit>/<name>`).
- The secret comes from Docker / Podman secrets (`/run/secrets/<name>`).
- The secret lives in a plain file with restricted permissions (mode `0600`, owned by the service user).

```yaml
password: !file /run/credentials/mcp-server-icinga/icinga2-prod-zh-password
```

If the path does not exist, is a directory, or cannot be read, the server fails fast with a clear error.

### Picking between `!env` and `!file`

Both are valid; mix them per backend if you want. Rules of thumb:

- **`!file`** scales better when you have many secrets across many instances. The MCP client config (`claude_desktop_config.json`) stays small, the secrets are managed by your existing credential store / systemd unit / container runtime, and the server process only sees the env vars it needs (mostly just `ICINGA_MCP_CONFIG`).
- **`!env`** is convenient for local development and for one-off secrets where wiring a file is overkill.

A common production pattern: an `EnvironmentFile=/etc/mcp-server-icinga/secrets.env` for a handful of well-known secrets, plus `!file /run/credentials/...` for everything that is per-instance and managed by systemd `LoadCredential=` or a vault-style mechanism.


## Multi-instance considerations

When you configure more than one instance, all instance-aware tools (the catalog tools today are global, the live Icinga tools that follow are not) take an `instance` parameter. With one instance, the parameter is optional and the single instance is auto-selected. With multiple, the LLM is instructed to ask which instance you mean, or you can name it directly in your prompt:

> What is currently red on the `prod-zh` instance?

> Compare the load on `app01` between `prod-zh` and `prod-fr`.

The instance name is part of the configuration's contract: rename it and every prompt that referenced it has to change.


## Where to go next

- [Quickstart with Claude](04 - Quickstart with Claude.md): wire the server into Claude Desktop or Claude Code and run the first tool.
- [How Tool Discovery Works](05 - How Tool Discovery Works.md): under-the-hood walk-through of what happens between writing a Python function and Claude calling it.
