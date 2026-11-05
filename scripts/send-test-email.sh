#!/usr/bin/env bash
# POST a sample customer email (raw RFC 822) to an email inbox's inbound endpoint, the way
# a mail provider's webhook would, so the inbound channel can be tried without real mail.
#   scripts/send-test-email.sh <inbound-token> [from-address]
#   make send-test-email TOKEN=<inbound-token>
# The token is shown once, when you rotate it in Settings > Inboxes (an email inbox).
# Replying from the agent app then lands in Mailpit (http://localhost:4825).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN="${1:?usage: scripts/send-test-email.sh <inbound-token> [from-address]}"
FROM="${2:-}"; FROM="${FROM:-jamie.rivera@example.com}"
port="$(grep -s '^SD_API_PORT=' "$ROOT/deploy/compose/.env" | cut -d= -f2 || true)"
API="${SD_API_URL:-http://localhost:${port:-4830}}"
[[ "$TOKEN" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "the token has unexpected characters" >&2; exit 1; }

msgid="<$(date +%s).$RANDOM@example.com>"
mail="$(cat <<MAIL
From: Jamie Rivera <$FROM>
To: Support <support@supportdesk.local>
Subject: My bulb will not pair with the Bridge
Date: $(LC_ALL=C date -u '+%a, %d %b %Y %H:%M:%S +0000')
Message-ID: $msgid
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Hi,

I bought a Lumen Bulb 3 yesterday and it will not pair with my Lumen Bridge. The bulb
blinks twice and then nothing happens. I already tried turning it off and on again.

Could you help?

Thanks,
Jamie
MAIL
)"
printf '%s\n' "$mail" | \
  curl -sS --fail-with-body -X POST -H 'Content-Type: message/rfc822' --data-binary @- \
    "$API/api/v1/channels/email/inbound/$TOKEN"
echo
