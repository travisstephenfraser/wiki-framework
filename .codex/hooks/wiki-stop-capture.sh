#!/usr/bin/env bash
# Fires on the Codex Stop event.
# Reads the session transcript; if significant work happened (file changes or
# substantial shell activity), asks the agent to run /wiki-capture --quick so
# findings aren't silently lost at session end.
#
# Exit 0 → no-op (nothing worth capturing, or hook suppressed).
# Exit 2 → stderr content is fed back as a user message, triggering capture.
# Note: Stop hooks deliver rewake content via stderr, not stdout.
#
# The stop_hook_active flag in the payload prevents re-entry (this hook won't
# fire again for the follow-up capture turn).
#
# ---------------------------------------------------------------------------
# Why this is not a copy of .claude/hooks/wiki-stop-capture.sh
#
# The Claude copy counts Write/Edit/NotebookEdit tool_use blocks and pattern-
# matches Bash commands. Codex records a session completely differently: its
# rollout files (~/.codex/sessions/**/rollout-*.jsonl) carry
#   event_msg → payload.item_completed → item.type ∈ {FileChange,
#                                                     CommandExecution, ...}
# and tool calls appear as response_item/custom_tool_call (name "exec", whose
# input may wrap an apply_patch) or response_item/function_call. None of those
# are the shapes the Claude script looks for, so running it verbatim against a
# Codex transcript counts zero forever — the same silent undercount the Claude
# copy was fixed on 2026-08-13 to avoid, reintroduced by a different route.
#
# So both schemas are parsed here, and the counter is biased to OVER-count in
# both. The failure directions are not symmetric: a false positive costs one
# capture prompt that /wiki-capture's own KEEP/SKIP gate discards, while a
# false negative silently loses the session's findings. For the same reason, a
# transcript that parses but matches NO known event shape is treated as
# "unknown, probably work happened" and fires, rather than reporting a
# confident zero. A counter that cannot recognise its input must not look
# like a quiet session.
# ---------------------------------------------------------------------------

set -euo pipefail

INPUT=$(cat)

# Suppress if already in a stop-hook-triggered turn (prevents infinite loops)
IS_HOOK_TURN=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print('1' if d.get('stop_hook_active') else '0')
" 2>/dev/null || echo "0")
[[ "$IS_HOOK_TURN" == "1" ]] && exit 0

# Fire at most once per session — sentinel keyed to session id.
SESSION_ID=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(d.get('session_id') or d.get('thread_id') or '')" 2>/dev/null || echo "")
SENTINEL=""
if [[ -n "$SESSION_ID" ]]; then
  SENTINEL="${TMPDIR:-/tmp}/wiki-stop-capture-${SESSION_ID}.done"
  [[ -f "$SENTINEL" ]] && exit 0
fi

# Locate the transcript. Codex's Stop payload is not guaranteed to carry
# transcript_path, so fall back to the rollout for this session id, then to the
# newest rollout touched in the last hour.
TRANSCRIPT_PATH=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(d.get('transcript_path') or d.get('rollout_path') or '')
" 2>/dev/null || echo "")

if [[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]]; then
  CODEX_SESSIONS="${CODEX_HOME:-$HOME/.codex}/sessions"
  if [[ -d "$CODEX_SESSIONS" ]]; then
    if [[ -n "$SESSION_ID" ]]; then
      TRANSCRIPT_PATH=$(find "$CODEX_SESSIONS" -name "rollout-*${SESSION_ID}*.jsonl" -type f 2>/dev/null | head -1)
    fi
    if [[ -z "$TRANSCRIPT_PATH" ]]; then
      TRANSCRIPT_PATH=$(find "$CODEX_SESSIONS" -name 'rollout-*.jsonl' -type f -mmin -60 2>/dev/null \
        | xargs ls -t 2>/dev/null | head -1)
    fi
  fi
fi

[[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]] && exit 0

# Count meaningful activity across both transcript schemas.
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

file_writes = 0     # exact: an explicit file-change record or editor tool call
shell_writes = 0    # estimated: a shell command that plausibly wrote to disk
shell_calls = 0     # any shell invocation
recognised = 0      # events matching a schema we understand
lines = 0

# Conservative-in-the-safe-direction: any of these in a shell command means the
# call plausibly wrote to disk. Redirects to /dev/null and fd dups are excluded
# so `cmd 2>/dev/null` is not counted as a write.
WRITE_PATTERNS = re.compile(
    r"""(?:
          \btee\b
        | \bsed\b[^|;&]*\s-i
        | \b(?:cp|mv|rm|mkdir|rmdir|touch|ln|install|rsync|truncate|chmod|chown)\b
        | \bgit\s+(?:commit|apply|checkout|restore|reset|rm|mv|clean|stash)\b
        | \b(?:npm|pnpm|yarn|pip|pip3|cargo|go|brew)\s+(?:install|add|remove|uninstall)\b
        | \bwrite_text\b | \bwritelines\b | \bFile\.write\b | \bfs\.write
        | \bapply_patch\b
        | \bopen\s*\([^)]*['"][wax]
        | >>? \s* (?!\s*&?\s*/dev/null\b)(?!&\s*[0-9])
    )""",
    re.X,
)


def scan_shell(cmd):
    global shell_calls, shell_writes
    shell_calls += 1
    if WRITE_PATTERNS.search(cmd):
        shell_writes += 1


with open(path, errors="replace") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        lines += 1
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        etype = entry.get("type")
        payload = entry.get("payload")
        payload = payload if isinstance(payload, dict) else {}

        # ---- Codex rollout schema -------------------------------------
        if etype == "event_msg" and payload.get("type") == "item_completed":
            item = payload.get("item") or {}
            itype = item.get("type")
            if itype == "FileChange":
                recognised += 1
                changes = item.get("changes") or {}
                file_writes += max(1, len(changes))
            elif itype == "CommandExecution":
                recognised += 1
                cmd = item.get("command")
                if isinstance(cmd, list):
                    cmd = " ".join(str(c) for c in cmd)
                scan_shell(cmd or "")
            continue

        if etype == "response_item":
            ptype = payload.get("type")
            if ptype in ("custom_tool_call", "function_call"):
                recognised += 1
                name = payload.get("name") or ""
                blob = payload.get("input") or payload.get("arguments") or ""
                if not isinstance(blob, str):
                    blob = json.dumps(blob)
                if "apply_patch" in blob:
                    file_writes += 1
                elif name in ("exec", "exec_command", "shell", "local_shell"):
                    scan_shell(blob)
            continue

        # ---- Claude Code transcript schema ----------------------------
        msg = entry.get("message") or {}
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            for block in msg.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                recognised += 1
                name = block.get("name", "")
                if name in ("Write", "Edit", "NotebookEdit"):
                    file_writes += 1
                elif name == "Bash":
                    scan_shell((block.get("input") or {}).get("command", "") or "")

print(file_writes, shell_writes, shell_calls, recognised, lines)
PYEOF

COUNTS=$(cat "$COUNTS_FILE")
FILE_WRITES=$(echo "$COUNTS" | awk '{print $1}')
SHELL_WRITES=$(echo "$COUNTS" | awk '{print $2}')
SHELL_CALLS=$(echo "$COUNTS" | awk '{print $3}')
RECOGNISED=$(echo "$COUNTS" | awk '{print $4}')
LINES=$(echo "$COUNTS" | awk '{print $5}')

TOTAL_WRITES=$(( ${FILE_WRITES:-0} + ${SHELL_WRITES:-0} ))

fire() {
  [[ -n "$SENTINEL" ]] && : > "$SENTINEL" 2>/dev/null || true
  echo "$1" >&2
  exit 2
}

# A transcript with content but no recognisable events means the format moved.
# Fire rather than report a confident zero: an unrecognised schema is exactly
# how this hook silently stopped working before.
if [[ "${RECOGNISED:-0}" -eq 0 && "${LINES:-0}" -ge 20 ]]; then
  fire "Session ended. The transcript format was not recognised by the capture hook, so activity could not be measured; treating it as work rather than as a quiet session. Please run /wiki-capture --quick now, and note that .codex/hooks/wiki-stop-capture.sh needs its parser updated."
fi

# Trigger if anything plausibly wrote to disk, or on ≥ 4 shell calls
# (suggesting investigation worth preserving).
if [[ "${TOTAL_WRITES:-0}" -ge 1 ]] || [[ "${SHELL_CALLS:-0}" -ge 4 ]]; then
  fire "Session ended with ~${TOTAL_WRITES} file-writing call(s) (${FILE_WRITES} recorded as file changes, ${SHELL_WRITES} inferred from shell commands — the shell figure is a pattern-match estimate, not exact) and ${SHELL_CALLS} shell call(s) total. Please run /wiki-capture --quick now to preserve any reusable findings before this context closes."
fi

exit 0
