#!/usr/bin/env bash
# LLM Wiki Autopilot installer and updater.
#
#   ./install.sh --vault ~/Vault [--lang en|tr] [--machine NAME] [--remote GIT_URL]
#                [--timer] [--dashboard] [--no-hooks] [--no-skill]
#
# New folder: creates the vault from template/. Existing vault: copies the current tool, dashboard and skill
# into <vault>/99-Meta/System/ (other machines get them on their next pull). Then runs `vm install`.
set -eu

REPO="$(cd "$(dirname "$0")" && pwd -P)"
VAULT=""
LANG_ARG=""
MACHINE=""
REMOTE=""
VM_FLAGS=()

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
die() { echo "error: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --vault) VAULT="${2:-}"; shift 2 ;;
    --lang) LANG_ARG="${2:-}"; shift 2 ;;
    --machine) MACHINE="${2:-}"; shift 2 ;;
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --timer|--dashboard|--no-hooks|--no-skill) VM_FLAGS+=("$1"); shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done

command -v git >/dev/null 2>&1 || die "git is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || die "Python 3.9 or newer is required"
case "$(uname -s)" in Darwin|Linux) ;; *) die "only macOS and Linux are supported" ;; esac
command -v claude >/dev/null 2>&1 || echo "note: the Claude Code CLI (claude) is not on PATH; the worker needs it to write pages."

if [ -z "$VAULT" ] && [ -f "$HOME/.vault-memory/config.json" ]; then
  VAULT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("vault",""))' "$HOME/.vault-memory/config.json" 2>/dev/null || true)"
fi
[ -n "$VAULT" ] || die "pass --vault PATH (for example --vault ~/Vault)"
case "$VAULT" in "~"*) VAULT="$HOME${VAULT#\~}" ;; esac
mkdir -p "$VAULT"
VAULT="$(cd "$VAULT" && pwd -P)"
SYS="$VAULT/99-Meta/System"

# Language: --lang, else the vault's setting, else a Turkish legacy vault, else English.
current_lang() {
  python3 - "$SYS/config.json" "$VAULT" <<'PY'
import json, os, sys
try:
    lang = json.load(open(sys.argv[1])).get("language", "")
except Exception:
    lang = ""
if lang not in ("en", "tr"):
    bases = os.path.join(sys.argv[2], "99-Meta", "Bases")
    tr = os.path.exists(os.path.join(bases, "Oturumlar.base")) and not os.path.exists(os.path.join(bases, "Sessions.base"))
    lang = "tr" if tr else ""
print(lang)
PY
}
EXISTING_LANG="$(current_lang)"
LANG_SET="${LANG_ARG:-${EXISTING_LANG:-en}}"
case "$LANG_SET" in en|tr) ;; *) die "--lang must be en or tr" ;; esac
if [ -n "$EXISTING_LANG" ] && [ -n "$LANG_ARG" ] && [ "$LANG_ARG" != "$EXISTING_LANG" ]; then
  echo "note: switching the vault language from $EXISTING_LANG to $LANG_ARG; existing pages keep their language."
fi

NEW_VAULT=0
if [ ! -f "$VAULT/CLAUDE.md" ]; then
  NEW_VAULT=1
  echo "Creating vault in $VAULT ($LANG_SET)"
  # -n: never overwrite files that are already there (adopting an existing Obsidian vault)
  cp -Rn "$REPO/template/common/." "$VAULT/"
  cp -Rn "$REPO/template/$LANG_SET/." "$VAULT/"
  if [ -f "$VAULT/log.md" ]; then
    TODAY="$(date +%Y-%m-%d)"
    sed "s/{{date}}/$TODAY/g" "$VAULT/log.md" > "$VAULT/log.md.tmp" && mv "$VAULT/log.md.tmp" "$VAULT/log.md"
  fi
fi

if ! git -C "$VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$VAULT" init -q -b main 2>/dev/null || { git -C "$VAULT" init -q && git -C "$VAULT" checkout -q -b main; }
fi
if [ -n "$REMOTE" ]; then
  if git -C "$VAULT" remote get-url origin >/dev/null 2>&1; then
    git -C "$VAULT" remote set-url origin "$REMOTE"
  else
    git -C "$VAULT" remote add origin "$REMOTE"
  fi
fi

# Tool, dashboard and the skill for the vault language.
mkdir -p "$SYS/bin" "$SYS/dashboard" "$SYS/skill"
cp "$REPO/system/bin/vm" "$REPO/system/bin/vault_memory.py" "$SYS/bin/"
chmod +x "$SYS/bin/vm" "$SYS/bin/vault_memory.py"
rm -rf "$SYS/bin/__pycache__"
cp "$REPO/system/dashboard/server.py" "$REPO/system/dashboard/index.html" "$SYS/dashboard/"
SKILL_NAME="vault-memory"; [ "$LANG_SET" = "tr" ] && SKILL_NAME="vault-hafiza"
for d in vault-memory vault-hafiza; do rm -rf "$SYS/skill/$d"; done
cp -R "$REPO/skills/$SKILL_NAME" "$SYS/skill/$SKILL_NAME"

python3 - "$SYS/config.json" "$LANG_SET" <<'PY'
import json, sys
path, lang = sys.argv[1], sys.argv[2]
try:
    cfg = json.load(open(path))
except Exception:
    cfg = {}
if cfg.get("language") != lang:
    cfg["language"] = lang
    with open(path, "w") as f:
        f.write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
PY

VM="$SYS/bin/vm"
INSTALL_ARGS=()
[ -n "$MACHINE" ] && INSTALL_ARGS+=(--machine "$MACHINE")
"$VM" install ${INSTALL_ARGS[@]+"${INSTALL_ARGS[@]}"} ${VM_FLAGS[@]+"${VM_FLAGS[@]}"}
"$VM" index >/dev/null

if [ "$NEW_VAULT" = 1 ]; then
  git -C "$VAULT" add -A
  if git -C "$VAULT" commit -q -m "vault-memory: new vault"; then
    if [ -n "$REMOTE" ]; then
      git -C "$VAULT" push -q -u origin HEAD || echo "note: push failed; check the remote, then run: vm sync"
    fi
  else
    echo "note: initial commit failed (set git user.name and user.email), then run: vm sync"
  fi
else
  "$VM" sync || true
fi

cat <<EOF

LLM Wiki Autopilot is ready.
  vault:     $VAULT ($LANG_SET)
  command:   ~/.vault-memory/bin/vm   (add ~/.vault-memory/bin to PATH to type just "vm")
  dashboard: vm dashboard
  status:    vm status
Sessions are recorded about 20 minutes after they end.
EOF
