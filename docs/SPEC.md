# Vault Memory: format and interface spec

This file is the contract between the CLI (`system/bin/vault_memory.py`), the dashboard
(`system/dashboard/`), the vault template (`template/`) and the skills (`skills/`).
Change it together with the code.

## Pieces and where they live

| Repo path | Installed to | What |
|---|---|---|
| `system/bin/vm`, `system/bin/vault_memory.py` | `<vault>/99-Meta/System/bin/` (symlinked as `~/.vault-memory/bin`) | CLI, worker, hooks. Python 3.9+ stdlib only. |
| `system/dashboard/server.py`, `index.html` | `<vault>/99-Meta/System/dashboard/` | Local dashboard, started with `vm dashboard`. |
| `skills/vault-memory/` (en), `skills/vault-hafiza/` (tr) | `<vault>/99-Meta/System/skill/<name>/`, then `~/.claude/skills/<name>/` | Agent skill for the vault language. |
| `template/common/`, `template/<lang>/` | the new vault | Vault skeleton (rules, page templates, Obsidian config). |
| `install.sh` | – | Creates the vault if needed, copies `system/` + skill into it, runs `vm install`. |

The tool lives inside the vault, so every machine that pulls the vault runs the same version.

## Configuration

- Shared, per vault: `<vault>/99-Meta/System/config.json`. Keys: `language` (`en` | `tr`), `timezone`,
  `idle_minutes`, `gap_cap_minutes`, `model`, and the other defaults in `DEFAULTS`.
- Per machine: `~/.vault-memory/config.json` (`$VAULT_MEMORY_HOME`). Keys: `vault`, `machine`, `claude_bin`,
  `path`, `capture`, `process_remote`. Per-machine values override shared ones.
- `vault`, `machine`, `claude_bin`, `path`, `setting_sources`, `capture`, `process_remote` are machine-only:
  `load_config` ignores them in the shared config.
- Default `language` is `en`. Missing `language` in an existing vault means `en`; the Turkish vault sets `"language": "tr"`.

## Vault layout (same folder names in every language)

```
index.md, log.md, CLAUDE.md, AGENTS.md
00-Inbox/  01-Journal/Daily/  03-Areas/
02-Projects/PRJ-<slug>/PRJ-<slug>.md
02-Projects/PRJ-<slug>/{sessions,decisions,meetings,notes}/
04-Resources/{Topics,Entities,Sources,Syntheses,Snippets}/
05-Raw/{clippings,files,assets}/  05-Raw/sessions/YYYY/YYYY-MM/
99-Meta/{Templates,Bases,Lint,System}/
```

## Language-dependent strings

| Key | en | tr |
|---|---|---|
| minutes unit in headings | `min` | `dk` |
| no-project scope (file name, log scope) | `general` | `genel` |
| session section labels | `Request`, `Done`, `Decisions`, `Open items` | `İstek`, `Yapılanlar`, `Kararlar`, `Açık işler` |
| project page sections | `Summary`, `Status`, `Open items`, `Decisions`, `Good to know`, `Sessions` | `Özet`, `Durum`, `Açık işler`, `Kararlar`, `Bilinmesi gerekenler`, `Oturumlar` |
| project status values | `active`, `paused`, `done` | `aktif`, `beklemede`, `bitti` |
| sessions base file / project view | `Sessions.base`, view `Project` | `Oturumlar.base`, view `Proje` |
| skill name / context tag | `vault-memory` / `<vault-memory>` | `vault-hafiza` / `<vault-hafiza>` |
| redaction mask | `[REDACTED]` | `[GİZLENDİ]` |

Readers (dashboard, `recount`, `report`) accept both languages' units and labels, so a vault that switched
language still parses.

## Write guard

Every `claude -p` call (`guarded_llm`) is wrapped in a snapshot of the protected paths: `99-Meta/**` except
`99-Meta/Lint/`, `CLAUDE.md`, `AGENTS.md`, `index.md`, `log.md`, every dot file and dot folder at the vault root
except `.trash/` and `.obsidian/workspace*`, and `.git/config`, `.git/hooks/`, `.git/info/`. Changes the agent made
to them (edits, new files, deletions, mode changes) are reverted before anything is committed, and an alert is set.

## Session file

Path: `02-Projects/PRJ-<slug>/sessions/<date> <slug> <machine>.md`, or
`05-Raw/sessions/YYYY/YYYY-MM/<date> <general|genel> <machine>.md` when the session belongs to no project.

```markdown
---
type: session
title: 2026-11-16 · PRJ-acme · laptop
description: Sessions in PRJ-acme on 2026-11-16 on laptop
project: "[[PRJ-acme]]"          # absent for no-project sessions
date: 2026-11-16
machine: laptop
minutes: 87                      # sum of the entries below; written by the script
sessions: 2                      # number of entries; written by the script
tools: [claude-code]
---

## 14:32 — Short title (42 min · claude-code)

**Request:** one or two sentences.
**Done:** what was done; key commands and files.
**Decisions:** decisions and why. Omitted when none.
**Open items:** what is left. Omitted when none.

- 16:05 · 3 min · codex · short session
```

Heading regex (both languages): `^## (\d{1,2}):(\d{2}) — (.+?) \((\d+) (?:min|dk) · ([^)]+)\)\s*$`
Short-entry regex: `^- (\d\d:\d\d) · (\d+) (?:min|dk) · ([^·]+?) · (.*)$`
Section line regex: `^\*\*([^*]+?):\*\*\s*(.*)$`; continuation lines and `- ` bullets belong to the last section.

`minutes` is active time with an agent: gaps between consecutive messages count up to `gap_cap_minutes`
(default 5). Parallel sessions are counted separately.

## log.md

`## [YYYY-MM-DD HH:MM] session | <PRJ-slug | general | genel> | <one line>` followed by
`- <N> <unit> · <machine> · <tool> · [[links]]`. Kinds: `session`, `ingest`.

## CLI

```
vm worker [--now] [--session ID] [--sync] [--max N]   process finished sessions, commit, push
vm tick                                              timer entry: capture, then worker
vm hook session-start|session-end|stop               Claude Code hook entry
vm report [--project P] [--from D --to D | --days N | --week this|last] [--detail] [--json]
vm status [--json]                                   queue, alert, last log lines
vm dashboard [--host 127.0.0.1] [--port 4747] [--no-open]
vm sync | vm index | vm lint | vm context [--cwd DIR]
vm ingest [--now] [--path P] [--dry-run]
vm backfill --days N [--project P] [--exclude X] [--dry-run]
vm baseline [--force] | vm digest PATH [--offset N] [--show]
vm config [KEY [VALUE]]
vm install [--machine NAME] [--timer] [--dashboard] [--no-hooks] [--no-skill]
vm uninstall [--keep-skill]
```

`vm status --json` (and `vault_memory.status_info(cfg)`) returns:
`{"vault", "machine", "language", "pending", "ready", "backfill", "alert", "last_log", "capture", "process_remote"}`
where `last_log` is the last line of `worker.log` (`YYYY-MM-DD HH:MM:SS message`) or `""`.

## Dashboard API

`server.py` imports `../bin/vault_memory.py` (falls back to `$VAULT_MEMORY_HOME/bin/`).

- `GET /api/data` → `{vault, lang, generated, gap_cap_minutes, projects: {id: {id, title, description, status, updated, repos}},
  days: [{date, project, machine, minutes, sessions, file}], sessions: [{id, date, start, title, minutes, tool, project,
  machine, file, request, done[], decisions[], open[], other[]}], warnings: []}`.
  Sessions with no project use project id `_none`.
- `GET /api/status` → `status_info` dict above.
- Binds to `127.0.0.1` by default. Read-only.
