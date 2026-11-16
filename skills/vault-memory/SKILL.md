---
name: vault-memory
description: Reads and writes the user's persistent memory, an Obsidian vault that Claude Code and Codex sessions are distilled into and that git keeps in sync across machines. Saves notes, decisions and lessons from the current session; answers questions about past work, project status and time spent; opens the local time dashboard; processes new sources; runs the vault health check; installs, upgrades or removes the system. Triggers include "save this to my vault", "remember this", "note this down", "where did we leave off", "what did we do last week on X", "how much time did I spend on X", "open my work dashboard", "process this source", "vault lint", "why isn't my memory updating", "set up vault memory", "upgrade vault memory".
---

# Vault memory

The user's persistent memory is an Obsidian vault, kept in sync across machines with git.

- Tool: `~/.vault-memory/bin/vm` (called `vm` below). If it does not exist, the system is not installed: go to **Setup**.
- Vault path: the `vault` field in `~/.vault-memory/config.json`.
- Rules: `CLAUDE.md` in the vault root. Read it before writing anything to the vault. If it conflicts with this skill, `CLAUDE.md` wins.

A background worker processes sessions on its own about 20 minutes after they go idle. Use this skill when the user doesn't want to wait, asks something from memory, or wants to install or change the system.

## Which operation

| The user says | Section |
|---|---|
| "Save this session", "put this in my vault" | Process this session now |
| "Remember this: …", a specific piece of content | Write a specific note |
| "Where did we leave off", "what did we do in X" | Answer from memory |
| "How much did I work", "what did I do last week" | Time report |
| "Open my dashboard" | Dashboard |
| "Process this article / PDF" | Process a source |
| "Check the vault", "lint" | Health check |
| "My memory isn't updating" | Troubleshooting |
| "Set up vault memory", "add this machine", "upgrade", "remove it" | Setup, Upgrade, Uninstall |

## Process this session now

1. Find the session id. The `<vault-memory>` block added to the context at session start has a "Session id" line.
2. Run the worker for this session. It can take a minute or two; use a timeout of at least 5 minutes:

   ```bash
   ~/.vault-memory/bin/vm worker --session <session id>
   ```

   If no id is available, `vm worker --now` processes every pending session.
3. Check what was written and report it:

   ```bash
   git -C "<vault path>" log -3 --stat --format='%h %s'
   ```

   Keep the report short: which pages were created or updated (vault-relative paths) and the push status.

The command processes the session up to this moment. If the session continues, the rest is processed later as a separate entry; running it again never writes the same part twice.

## Write a specific note

If the user said exactly what to save, don't wait for the worker; write it yourself:

1. Pick the right place according to `CLAUDE.md`. Check `index.md` and the relevant folder for a page on the same subject first; if there is one, update it.
2. If the place is unclear, write `00-Inbox/YYYY-MM-DD <subject>.md`.
3. Frontmatter is required. Never write secrets (keys, tokens, passwords).
4. Run `vm sync` and report the result.

## Answer from memory

1. Read `index.md` and find the relevant pages.
2. For a project question, read the project page first (`02-Projects/PRJ-<name>/PRJ-<name>.md`); for detail, read that project's `sessions/` files and the lines in `log.md` that contain `| PRJ-<name> |`.
3. Answer with vault-relative page paths. Don't invent what is not in the vault; if it isn't there, say there is no record.
4. If the answer has lasting value (a comparison, an analysis), offer to save it as a page under `04-Resources/Syntheses/`.

## Time report

Never compute time yourself; run the report:

```bash
~/.vault-memory/bin/vm report --project <name> --week last --detail
```

- `--week this|last`, or `--from YYYY-MM-DD --to YYYY-MM-DD`, or `--days 7`.
- Without `--project`, every project is listed. The project name matches partially.
- `--detail` also lists the session titles for each day. `--json` gives machine-readable output.

Tell the user that this is active time spent with an agent: time without an agent and long gaps between messages are not counted, and parallel sessions are counted separately. For charts and filters, offer the dashboard.

## Dashboard

```bash
~/.vault-memory/bin/vm dashboard            # http://127.0.0.1:4747, opens the browser
~/.vault-memory/bin/vm dashboard --port 4800 --no-open
```

It runs in the foreground until stopped; when you start it for the user, run it in the background and give them the address. The page reads the vault live and has an English/Turkish switch. To start it automatically at login: `vm install --dashboard`.

## Process a source

Follow the "Source processing" steps in `CLAUDE.md`: read the raw file without changing it, write a summary page under `04-Resources/Sources/`, update the pages the source touches, run `vm sync`. Report which pages you touched. `vm ingest` does the same for every new file in the inbox folders.

## Health check

1. Run `vm lint`; the report is written to `99-Meta/Lint/YYYY-MM-DD.md`.
2. Read the report and fill in its semantic check section: contradicting or outdated claims, pages that should be merged, concepts that appear often but have no page.
3. Make the safe fixes (missing frontmatter, broken links). Don't delete pages or move files; propose those in the report.
4. Run `vm sync` and summarize the findings.

## Troubleshooting

```bash
~/.vault-memory/bin/vm status
```

- Shows pending sessions, the last worker log lines and any alert. Full log: `~/.vault-memory/logs/worker.log`.
- Alert about a secret-like value blocking a commit: find the changed files with `git status` in the vault, remove the value, then run `vm sync`.
- Alert about a sync conflict: run `git pull --rebase` in the vault folder, resolve the conflicting file together with the user, then run `vm sync`.
- Hooks missing, or a newly set up machine: `<vault>/99-Meta/System/bin/vm install --machine <name>`.

## Setup

Only when `~/.vault-memory/bin/vm` does not exist, or the user asks to set the system up.

1. Ask the user, in one message:
   - Where the vault should live (default `~/Vault`; a new, empty folder is safest).
   - Language of the vault pages: `en` or `tr`.
   - Whether to sync it with a git remote. If yes, ask for the URL of an empty **private** repository; the vault holds summaries of their work.
   - Whether to install the 5-minute background timer (recommended; without it, sessions are processed only when a hook fires).
2. Get or update the source:

   ```bash
   if [ -d ~/.vault-memory/src/.git ]; then git -C ~/.vault-memory/src pull --ff-only; \
   else git clone https://github.com/yusufkaran/llm-wiki-autopilot ~/.vault-memory/src; fi
   ```

3. Install:

   ```bash
   ~/.vault-memory/src/install.sh --vault <path> --lang <en|tr> [--remote <git url>] [--timer]
   ```

   If this skill was loaded from a plugin (its base directory is under `~/.claude/plugins/`), add `--no-skill` so the skill is not installed twice.
4. Run `vm status` and report: vault path, machine name, hooks, timer. Tell the user that sessions are processed about 20 minutes after they go idle, and that sessions from before the installation are not imported unless they run `vm backfill --days N` (one LLM call per session).

**Another machine** (the vault already exists on a git remote):

```bash
git clone <remote url> ~/Vault
~/Vault/99-Meta/System/bin/vm install --machine <name> --timer
```

On a laptop that is often closed, `vm config capture true` sends redacted digests to the remote so an always-on machine can finish them; on that always-on machine, `vm config process_remote true`.

## Upgrade

```bash
git -C ~/.vault-memory/src pull --ff-only
~/.vault-memory/src/install.sh --vault <vault path>
~/.vault-memory/bin/vm sync
```

The installer copies the new scripts, dashboard and skill into the vault and keeps the vault's language and settings. `vm sync` pushes them, so other machines run the new version after their next pull.

## Uninstall

```bash
~/.vault-memory/bin/vm uninstall              # add --keep-skill to keep this skill
```

Removes the hooks, the timer, the dashboard service and the installed skill from this machine. The vault and its git history are never deleted.
