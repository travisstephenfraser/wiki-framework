#!/usr/bin/env bash
# Fires on Claude Code Stop event.
# Reads the session transcript; if significant work happened (file edits or
# substantial shell activity), asks Claude to run /wiki-capture --quick so
# findings aren't silently lost at session end.
#
# Exit 0 → no-op (nothing worth capturing, or hook suppressed).
# Exit 2 → stderr content is fed back to Claude as a user message, triggering capture.
# Note: Claude Code Stop hooks deliver rewake content via stderr, not stdout.
#
# The stop_hook_active flag in the payload prevents re-entry (this hook won't
# fire again for the follow-up capture turn).

set -euo pipefail

INPUT=$(cat)

# Suppress if already in a stop-hook-triggered turn (prevents infinite loops)
IS_HOOK_TURN=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('1' if d.get('stop_hook_active') else '0')
" 2>/dev/null || echo "0")
[[ "$IS_HOOK_TURN" == "1" ]] && exit 0

# Fire at most once per session — sentinel file keyed to session_id prevents
# repeated nudges after the threshold is crossed on the first turn.
SESSION_ID=$(printf '%s' "$INPUT" | python3 -c "
import json, sys; print(json.load(sys.stdin).get('session_id', ''))" 2>/dev/null || echo "")
SENTINEL=""
if [[ -n "$SESSION_ID" ]]; then
  SENTINEL="${TMPDIR:-/tmp}/wiki-stop-capture-${SESSION_ID}.done"
  [[ -f "$SENTINEL" ]] && exit 0
fi

TRANSCRIPT_PATH=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('transcript_path', ''))
" 2>/dev/null || echo "")

[[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]] && exit 0

# Count meaningful tool uses.
#
# Editor writes (Write/Edit/NotebookEdit) are exact. Shell writes are NOT: a
# session that does all its file mutation through Bash (bulk edits driven by a
# script, heredocs, sed -i, redirection) is invisible to a tool-name counter.
# That happened on 2026-08-13 — 27 vault files rewritten, reported as "0 file
# edit(s)" — and the failure direction is the flattering one: an undercount
# reads as "quiet session", which pushes /wiki-capture toward SKIP. So Bash
# commands are pattern-matched for filesystem mutation and folded into the
# total, biased to OVER-count. A false positive costs one capture prompt that
# the skill's own KEEP/SKIP gate then discards; a false negative silently loses
# the session's findings.
#
# NOTE: this heredoc is deliberately NOT wrapped in $( ). Bash's command-
# substitution scanner tokenizes the body looking for the closing paren, so a
# regex containing an unbalanced quote or a [^)] class breaks the parse with a
# confusing "unexpected EOF" pointing at a line far below. Redirect to a temp
# file instead and read it back.
COUNTS_FILE=$(mktemp "${TMPDIR:-/tmp}/wiki-stop-capture-counts.XXXXXX")
trap 'rm -f "$COUNTS_FILE"' EXIT

python3 - "$TRANSCRIPT_PATH" > "$COUNTS_FILE" <<'PYEOF'
import json, re, sys

path = sys.argv[1]
editor_writes = 0
shell_writes = 0
bash_count = 0

# Conservative-in-the-safe-direction: any of these in a Bash command means the
# call plausibly wrote to disk. Stderr/stdout redirects to /dev/null and simple
# fd dups are excluded so they don't mark every `cmd 2>/dev/null` as a write.
WRITE_PATTERNS = re.compile(
    r"""(?:
          \btee\b
        | \bsed\b[^|;&]*\s-i
        | \b(?:cp|mv|rm|mkdir|rmdir|touch|ln|install|rsync|truncate|chmod|chown)\b
        | \bgit\s+(?:commit|apply|checkout|restore|reset|rm|mv|clean|stash)\b
        | \b(?:npm|pnpm|yarn|pip|pip3|cargo|go|brew)\s+(?:install|add|remove|uninstall)\b
        | \bwrite_text\b | \bwritelines\b | \bFile\.write\b | \bfs\.write
        | \bopen\s*\([^)]*['"][wax]
        | >>? \s* (?!\s*&?\s*/dev/null\b)(?!&\s*[0-9])
    )""",
    re.X,
)

with open(path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name in ("Write", "Edit", "NotebookEdit"):
                editor_writes += 1
            elif name == "Bash":
                bash_count += 1
                cmd = (block.get("input") or {}).get("command", "") or ""
                if WRITE_PATTERNS.search(cmd):
                    shell_writes += 1

print(editor_writes, shell_writes, bash_count)
PYEOF

COUNTS=$(cat "$COUNTS_FILE")

EDITOR_WRITES=$(echo "$COUNTS" | awk '{print $1}')
SHELL_WRITES=$(echo "$COUNTS" | awk '{print $2}')
BASH_COUNT=$(echo "$COUNTS" | awk '{print $3}')
FILE_WRITES=$(( ${EDITOR_WRITES:-0} + ${SHELL_WRITES:-0} ))

# Trigger if anything plausibly wrote to disk, or if there were ≥ 4 shell calls
# (suggesting investigation/debugging worth preserving).
if [[ "${FILE_WRITES:-0}" -ge 1 ]] || [[ "${BASH_COUNT:-0}" -ge 4 ]]; then
  [[ -n "$SENTINEL" ]] && : > "$SENTINEL" 2>/dev/null || true
  echo "Session ended with ~${FILE_WRITES} file-writing call(s) (${EDITOR_WRITES} via editor, ${SHELL_WRITES} via shell — the shell figure is a pattern-match estimate, not exact) and ${BASH_COUNT} shell call(s) total. Please run /wiki-capture --quick now to preserve any reusable findings before this context closes." >&2
  exit 2
fi

exit 0
