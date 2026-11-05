#!/usr/bin/env bash
# Write deploy/demo-site/site/config.js (git-ignored) with the seeded Lumen organisation's
# public widget key, so the demo customer site on http://localhost:4815 loads the widget.
#   scripts/demo-site-config.sh [api-url]      (default http://localhost:4830)
# `make demo` runs it right after the seed. The key is public by design (it identifies the
# inbox; the inbox's allowed origins decide where it works).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${1:-http://localhost:4830}"
WEB="${SD_WIDGET_SRC:-http://localhost:${SD_WEB_PORT:-4810}/widget.js}"
OUT="$ROOT/deploy/demo-site/site/config.js"

body="$(curl -sf "$API/api/v1/help/lumen")" || {
  echo "could not read $API/api/v1/help/lumen: is the stack up and the demo seeded?" >&2
  exit 1
}
key="$(printf '%s' "$body" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("widget_key") or "")')"
if [[ ! "$key" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "the Lumen help center has no widget key (is its website chat inbox active?)" >&2
  exit 1
fi
cat > "$OUT" <<JS
// Written by \`make demo\` (scripts/demo-site-config.sh). Local only, git-ignored.
window.SUPPORTDESK_WIDGET_KEY = "$key";
window.SUPPORTDESK_WIDGET_SRC = "$WEB";
window.SUPPORTDESK_API_URL = "$API";
JS
echo "  demo site widget key written to deploy/demo-site/site/config.js"
