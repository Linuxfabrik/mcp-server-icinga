# Contributing


## Linuxfabrik Standards

The following standards apply to all Linuxfabrik repositories.


### Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).


### Issue Tracking

Open issues are tracked on GitHub Issues in the respective repository.


### Pre-commit

Some repositories use [pre-commit](https://pre-commit.com/) for automated linting and formatting checks. If the repository contains a `.pre-commit-config.yaml`, install [pre-commit](https://pre-commit.com/#install) and configure the hooks after cloning:

```bash
pre-commit install
```


### Commit Messages

Commit messages follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification:

```
<type>(<scope>): <subject>
```

If there is a related issue, append `(fix #N)`:

```
<type>(<scope>): <subject> (fix #N)
```

`<type>` must be one of:

- `chore`: Changes to the build process or auxiliary tools and libraries
- `docs`: Documentation only changes
- `feat`: A new feature
- `fix`: A bug fix
- `perf`: A code change that improves performance
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `style`: Changes that do not affect the meaning of the code (whitespace, formatting, etc.)
- `test`: Adding missing tests


### Changelog

Document all changes in `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Sort entries within sections alphabetically.

The audience is a Linux system engineer with 30 seconds to decide whether an update is worth it. Write for that reader:

* **Lead with highlights.** Begin every release section with three to five sentences of running text, directly below the version heading and above the first `###` section. Cover what drives the update decision, including any manual step it requires. No bullet list, no issue links, no repetition of the individual entries. A release with only a handful of entries does not need one, since the entries themselves already fit on a screen.
* **State the change before its scope.** Up to five affected components keep the `component: what changed` form. From six on, put the statement first and close it with either a collective name (`all *-version checks`) or the components in parentheses, so the entry is understood from its first line. These broad entries come first in their subsection, ahead of the alphabetically sorted per-component entries.
* **One sentence per entry.** `Added`, `Changed` and `Fixed` say what an administrator notices. Root cause, reproduction steps and internal reasoning belong in the commit body and the issue.
* **Migration instructions only under `Breaking Changes`.** Wording such as "rename x to y" or "set z to restore the previous behaviour" anywhere else means the entry sits in the wrong section. Entries under `Breaking Changes` may run longer than one sentence.
* **Leave out contributor-only changes.** Lockfile and pin bumps, Dependabot and pre-commit configuration, GitHub Actions bumps and test infrastructure are covered by the git history and the pull request. Keep an entry only where an administrator sees the effect, for example when it changes the released artifact.

A release section starts like this:

```markdown
## [v6.1.0] - 2026-09-15

**Highlights:** Two long-standing sources of false alarms are gone, and container workloads are now covered. Cumulative counters are reported as rates instead of totals, so any dashboard built on them has to be re-imported.

### Added
```

The scope rule, on an entry affecting 43 components. Instead of:

```markdown
* about-me, borgbackup, deb-lastactivity, file-ownership, fs-xfs-stats, getent, ...: `--always-ok` to force an OK result
```

write:

```markdown
* `--always-ok` forces an OK result on 43 further components (about-me, borgbackup, deb-lastactivity, ...)
```


### Language

Code, comments, commit messages, and documentation must be written in English.


### CI Supply Chain

GitHub Actions in `.github/workflows/` are pinned by commit SHA, not by tag. Dependabot's `github-actions` ecosystem keeps these pins up to date.

Python packages installed via `pip` inside workflows follow a two-tier policy:

- `pre-commit` is installed from a hash-pinned requirements file at `.github/pre-commit/requirements.txt`, generated with `pip-compile --generate-hashes --strip-extras` from `.github/pre-commit/requirements.in`. Dependabot's `pip` ecosystem watches that directory and maintains both files.
- One-shot installs such as `ansible-builder`, `build`, `mkdocs`, `pdoc`, and `ruff` in release, docs, or test workflows are version-pinned only (`package==X.Y.Z`) and kept fresh by Dependabot. Scorecard's `pipCommand not pinned by hash` findings for these are considered acceptable risk and may be dismissed.


### Coding Conventions

- Sort variables, parameters, lists, and similar items alphabetically where possible.
- Always use long parameters when using shell commands.
- Use RFC [5737](https://datatracker.ietf.org/doc/html/rfc5737), [3849](https://datatracker.ietf.org/doc/html/rfc3849), [7042](https://datatracker.ietf.org/doc/html/rfc7042#section-2.1.1), and [2606](https://datatracker.ietf.org/doc/html/rfc2606) in examples and documentation:
    - IPv4: `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`
    - IPv6: `2001:DB8::/32`
    - MAC: `00-00-5E-00-53-00` through `00-00-5E-00-53-FF` (unicast), `01-00-5E-90-10-00` through `01-00-5E-90-10-FF` (multicast)
    - Domains: `*.example`, `example.com`


---


## mcp-server-icinga Guidelines


### Project Status

This project is in early development. Code layout, configuration surface and tool inventory are expected to change. Until the first release is cut, breaking changes may land on `main` without deprecation notice. Pin to a commit SHA if you depend on it during this phase.


### Commit Scopes

Common scopes for this project:

- `feat(core):` -- Icinga 2 Core REST client / tools
- `feat(web):` -- Icinga Web / Icinga DB Web REST client / tools
- `feat(director):` -- Icinga Director REST client / tools
- `feat(plugins):` -- Linuxfabrik monitoring-plugins catalog (parsing, lookup)
- `feat(tsdb):` -- time series database integration (default: InfluxDB)
- `feat(server):` -- MCP server entrypoint, transport, tool registration
- `feat(config):` -- environment / configuration handling
- `chore:` -- maintenance (dependencies, CI, formatting)
- `docs:` -- documentation changes
- `fix(<scope>):` -- bug fix in the named scope
- `refactor:` -- code restructuring without behaviour change
- `test:` -- test additions or fixture changes


### Developer Guide

Detailed developer documentation lives in [`docs/developer-guide/`](docs/developer-guide/), starting with a [Source Layout](<docs/developer-guide/01 - Source Layout.md>) walkthrough of every file under `src/`.
