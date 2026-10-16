#!/bin/bash
# install-vault-hooks.sh — install the hub-contract pre-commit hook for a wiki vault repo.
#
#   scripts/install-vault-hooks.sh <vault-repo>
#
# Copies obsidian_wiki/hub_contract.py from THIS checkout into a local, untracked hooks
# directory (default ~/.config/vault-hooks; never inside the synced vault, so a push from
# another machine can never change code that runs here), records its sha256 and the
# framework commit, writes a pre-commit hook, and points the vault's core.hooksPath at it.
# The hook never reads the framework working tree; re-run this after reviewing a new
# checker version.
#
# Env: VAULT_HOOKS_DIR (install dir), VAULT_HOOKS_PYTHON (interpreter; stdlib only, >=3.9).
set -euo pipefail

VAULT=${1:?usage: install-vault-hooks.sh <vault-repo>}
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST=${VAULT_HOOKS_DIR:-$HOME/.config/vault-hooks}
PY=${VAULT_HOOKS_PYTHON:-$(command -v python3)}

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

git -C "$VAULT" rev-parse --git-dir >/dev/null
if [ -n "$(git -C "$HERE" status --porcelain -- obsidian_wiki/hub_contract.py)" ]; then
  echo "refusing: hub_contract.py has uncommitted changes; install only reviewed, committed code" >&2
  exit 1
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || { echo "refusing: $PY is older than Python 3.9" >&2; exit 1; }

existing=$(git -C "$VAULT" config --get core.hooksPath || true)
if [ -n "$existing" ] && [ "$existing" != "$DEST" ]; then
  echo "refusing: $VAULT already sets core.hooksPath=$existing" >&2
  exit 1
fi
if [ -z "$existing" ]; then
  # core.hooksPath replaces .git/hooks entirely; never silently disable a real hook.
  hookdir=$(cd "$VAULT" && cd "$(git rev-parse --git-path hooks)" && pwd)
  for h in "$hookdir"/*; do
    case "$h" in *.sample) ;; *) [ -e "$h" ] && { echo "refusing: existing hook $h would be bypassed" >&2; exit 1; } ;; esac
  done
fi

mkdir -p "$DEST"
cp "$HERE/obsidian_wiki/hub_contract.py" "$DEST/hub_contract.py"
sha=$(sha256 "$DEST/hub_contract.py")
printf 'sha256=%s\ncommit=%s\npython=%s\ninstalled=%s\n' \
  "$sha" "$(git -C "$HERE" rev-parse HEAD)" "$PY" "$(date '+%Y-%m-%dT%H:%M:%S%z')" > "$DEST/PINNED"

cat > "$DEST/pre-commit" <<'HOOK'
#!/bin/bash
# Vault pre-commit: enforce hub contracts on the STAGED tree (installed by install-vault-hooks.sh).
# Guards mistakes, not an adversary: `git commit --no-verify` skips it.
set -u
DIR=$(cd "$(dirname "$0")" && pwd)
PY=$(sed -n 's/^python=//p' "$DIR/PINNED")
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

# Inert unless the staged tree registers a contracted hub.
git cat-file -e :_meta/hub-contracts.json 2>/dev/null || exit 0

if [ "$(sed -n 's/^sha256=//p' "$DIR/PINNED")" != "$(sha256 "$DIR/hub_contract.py")" ]; then
  echo "Commit blocked: hub_contract.py does not match its pinned sha256; re-run install-vault-hooks.sh after review. Bypass deliberately with --no-verify."
  exit 1
fi
TMP=$(mktemp -d) || { echo "Commit blocked: mktemp failed. Bypass deliberately with --no-verify."; exit 1; }
trap 'rm -rf "$TMP"' EXIT
# checkout-index honours GIT_INDEX_FILE, so partial and `-a` commits check what will be committed.
git checkout-index -a --prefix="$TMP/" \
  || { echo "Commit blocked: could not export the index for the hub-contract check. Bypass deliberately with --no-verify."; exit 1; }
REPO=$(git rev-parse --show-toplevel)
# Roll check against the last commit; a repository with no commits yet has nothing to roll from.
SINCE=(); git rev-parse --verify --quiet HEAD >/dev/null && SINCE=(--since HEAD --repo "$REPO")
# env -i: no inherited credentials (e.g. a deploy key's GIT_SSH_COMMAND) reach the checker.
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin HOME="$HOME" "$PY" -I "$DIR/hub_contract.py" "$TMP" "${SINCE[@]}"
rc=$?
case $rc in
  0) exit 0 ;;
  3) echo; echo "Commit blocked: hub contract violation (above). Fix the routing, or bypass deliberately with --no-verify."; exit 1 ;;
  *) echo "Commit blocked: the hub-contract check could not run (exit $rc). Bypass deliberately with --no-verify."; exit 1 ;;
esac
HOOK
chmod +x "$DEST/pre-commit"
git -C "$VAULT" config core.hooksPath "$DEST"
echo "installed: $DEST (hub_contract.py sha256 $sha); $VAULT core.hooksPath -> $DEST"
