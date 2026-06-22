# Design Decisions

Significant architecture decisions and their rationale, in ADR style. Each entry records the context, the decision and its consequences so later contributors understand why the project is shaped the way it is.


## Local-only deployment

**Status:** accepted, 2026-06-22.

### Context

The server bridges a cloud LLM to Icinga over the Model Context Protocol. Two deployment shapes are technically possible:

- **Local stdio** (current): the MCP client spawns the server as a child process per operator, over stdin/stdout.
- **Hosted HTTP** (streamable-http): a long-running daemon at a URL such as `https://mcp-server-icinga.linuxfabrik.ch` that clients connect to directly.

A hosted service is attractive for its zero-install convenience: clients would just add a URL. The decisive factor is where the credentials live. The credential-bearing part of the server is the Icinga side: the server stores Icinga API credentials and uses them to authenticate against the Icinga REST APIs.

### Decision

The server is deployed locally and spawned by each operator's MCP client. The project does not ship or operate a shared hosted service.

### Rationale

- A hosted service would concentrate the Icinga credentials for every fronted instance in one internet-facing process. That is a high-value target, and authenticating to the endpoint would be equivalent to full access to every configured instance, including write actions.
- Keeping the server local means the Icinga credentials never leave the operator's own machine. They are used only to authenticate to Icinga over HTTPS and are never centralized in a third-party-hosted service.
- A **hybrid** was considered and rejected: host only the credential-free plugin catalog, keep the Icinga-facing tools local. It brings no advantage, because the Icinga tools already require a local install. Hosting only the catalog adds operational surface without removing the local-install requirement, so it delivers none of the zero-install benefit that motivates hosting in the first place.
- Network reachability (the server must reach the Icinga API, e.g. port 35665, possibly over a VPN) is handled per operator, which matches how access to Icinga is already granted.

### Consequences

- Each operator installs and configures the server and supplies their own Icinga credentials (see the [Configuration](../user-guide/03 - Configuration.md) guide).
- There is no shared endpoint to secure, no central secret store and no tenant isolation to build.
- A hosted service remains technically possible but is explicitly out of scope. It would require an authentication layer, a credential-custody or per-session-credential model, and, for several Icinga deployments, tenant isolation. None of that is built, and adopting it would be a separate, deliberate decision recorded here.


## What is and is not sent to Anthropic

A direct consequence of the deployment model above, and relevant to any operator assessing data exposure.

- **Icinga credentials are never sent to Anthropic.** They are loaded locally (from environment variables or files via the `!env` / `!file` tags), held only in the local server process, and used only to set the HTTP authentication header on requests to the Icinga REST APIs. They are not part of any tool result and are not included in the messages the MCP client forwards to the model. In the code, the resolved secret values are read only where the HTTP client builds its auth tuple; everywhere else the configuration is inspected with boolean checks, never by reading the secret.
- **Tool results are sent to Anthropic.** When Claude calls a tool, its result (host and service state, check output and perfdata, instance names, plugin metadata and plugin source) is returned to the MCP client and becomes part of the conversation the client sends to the Anthropic API, because that is how the model reasons about it. This is inherent to using a hosted LLM and is true whether the server runs locally or hosted.

In short: the **data** the server reads from Icinga is processed by Anthropic; the **credentials** that read it are not. Running the server locally does not change what data reaches the model, but it does guarantee that the credentials stay on the operator's machine.

Operators who consider the monitoring data itself too sensitive for a hosted model should point their MCP client at a locally or privately hosted model. That choice lives in the MCP client, not in this server, which only returns data to whatever client spawned it.
