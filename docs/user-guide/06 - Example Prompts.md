# Example Prompts

What you can ask depends on which backends you configured. The server advertises its tools to the LLM, so plain language is enough: you describe what you want, the model picks the tool. You never name a tool yourself.

A good habit is to open a session with a health check; it confirms, without touching the network, which instances and backends are wired up.

> Run a health check.


## Plugin catalog

These work as soon as `monitoring_plugins.catalog_path` points at a local checkout of the [monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins) repository (the `check-plugins/` directory). No Icinga connection is required, so they are the easiest first test.

> List all Linuxfabrik monitoring plugins.

> Which plugins run on Windows?

> Explain the `disk-usage` plugin: what does it check, which arguments does it take, and what perfdata does it emit?

> Which plugin backs the check command `cmd-check-disk-usage`?


## Live host and service state

These require an instance with a reachable `icinga2_core` backend. Name the instance in the prompt, or omit it when only one instance is configured and the server selects it automatically.

> What is currently not OK on `prod-zh`?

> Show all DOWN hosts on `prod-zh`.

> Which services are CRITICAL on `prod-zh`, and what did their last check output?

> Show the full state of host `db01` on `prod-zh`, including its last check output and perfdata.

> Investigate the problems on `prod-zh` and `prod-fr`.


## Root-cause bridge

The point of pairing live state with the plugin catalog is to explain a problem, not just report it. In one conversation the server can read the failing service, resolve its check command to a plugin, and explain what that plugin measures.

> Why is the `disk` service on `db01` critical, and what does that check actually measure?

> Go through every problem on `prod-zh` and, for each failing service, explain what its check does and which thresholds it uses.


## Acting on problems

These require an instance with write credentials (`write_username` / `write_password`). Without them the action tools are not offered at all, so a read-only deployment stays read-only. Every action is attributed to the configured write user.

> Acknowledge the `disk` problem on `db01` with the comment "cleanup in progress".

> Schedule a two-hour downtime for host `db01` and all its services, comment "kernel upgrade".

> Remove the downtime from host `db01`.

> Recheck the `http` service on `web01` now.


## Where to go next

- [Configuration](03 - Configuration.md): wire up instances, backends and secrets so the prompts above have something to talk to.
- [Quickstart with Claude](04 - Quickstart with Claude.md): register the server in Claude Desktop or Claude Code.
