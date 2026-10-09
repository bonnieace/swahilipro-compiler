# CLI accounts and text chat (first implementation)

This implements the dispatch/account/read-only chat slices of the CLI agent plan.
The interpreter, REPL, check command, help/version aliases and stdin execution work
offline. Agent modules load only for an exact account/chat command. `swa run PATH`
is the explicit file form when a file is named `chat`, `login`, etc.; `./chat` also
works. Chat remains text-only. Explicit local tools and the editor stdio interface
are documented in [Engine protocol](engine-protocol.md); autonomous orchestration
and session resume remain future work.

## Setup

The companion Next.js backend must first have accounts, client grants, credits and
the Bedrock gateway deployed (web PRs #6, #7, #8). Configure its actual HTTPS origin:

```sh
swa configure --api-origin https://YOUR-DEPLOYED-HOST
swa login
swa whoami
swa credits
swa models
swa chat --model MODEL_ID --prompt 'Explain SwahiliPro functions'
swa chat --model MODEL_ID
swa logout
```

Use `login --no-browser` on a headless terminal; the URL and confirmation code are
always printed. Verify the matching code in the website approval page. Installation
never opens a browser or initiates sign-in. No credentials are supplied on command
lines. `chat --prompt TEXT --json` emits versioned JSON records; account commands
also support `--json`. Use `/exit` or Ctrl+C to leave interactive chat. Prompt text
passed on a command line can appear in shell history; use interactive chat for
sensitive text. Only text explicitly entered into this chat is uploaded.

There is intentionally no guessed production domain. Configuration is stored under
the user's profile, never loaded from a repository or an API-origin environment
variable. All credential requests use the configured HTTPS origin. Verification
URLs must match that origin and exact attempt ID. Redirects and inherited proxy
settings are disabled; standard bundled certificate verification stays enabled.
Changing origin selects a different credential namespace. This release supports
one active account per origin; logout before switching accounts.

## Credentials and recovery

Windows Credential Manager, macOS Keychain or Linux Secret Service stores the
credential bundle. These are explicit keyring backends; custom/plaintext fallback
plugins are not selected. A headless Linux machine needs an unlocked Secret Service
session. Failure to access a keychain fails closed; no credential file is created.

A per-origin process lock protects login, logout and token refresh. Refresh writes
a recovery marker to the keychain before sending the old credential. On a lost
response, crash or failed write of the rotated credential, the next command requires
logout and login instead of replaying the old refresh token. The backend revokes a
grant when a used refresh token is replayed. Logout clears the local bundle even
when remote revocation fails; its response then directs you to revoke the device
from the website. Cancelled login attempts expire on the server.

## Chat and credit status

This adapter supports the gateway's current text-only API and does not execute
model-suggested tools. Models and prices come from the server; `--model` is required.
Each turn is limited to 30 messages, a bounded body, 8,192 requested output tokens,
a bounded stream and connection/read timeouts. Backend model limits may be lower.
A new turn is never automatically retried after quota, network or stream errors.
After any failed interactive turn, chat exits rather than silently charging again.

Before sending a turn, the CLI writes a receipt outside the repository and prints
the request ID. It contains origin, account ID, idempotency key and outcome, but no
prompt, response or token. Request IDs use the backend's version-1 derivation, so
status remains available even when the first streamed event was lost:

```sh
swa request REQUEST_ID --json
```

Status recovery uses only GET requests and checks the current account against the
receipt. It cannot invoke a model. A settled request can still have missing output;
the server does not retain generated text for replay. `unknown` can mean credits
remain reserved until backend reconciliation or operator review. A 404 does not
justify an automatic paid retry: the original call might still be processing.
The user must explicitly start a new turn if a fresh paid response is desired.

Interactive conversation context exists only in memory. Receipts live in
`~/.local/share/swahilipro` (Linux), `~/Library/Application Support/SwahiliPro`
(macOS), or `~/AppData/Local/SwahiliPro` (Windows), under an origin hash. On POSIX,
directories/files are restricted to the user; on Windows they inherit user-profile
ACLs. No telemetry is added. Old receipts can be removed manually after resolving
their requests; deleting one does not cancel server work or refund credits.

Exit codes: existing runtime codes remain 0/1/2; account/setup usage errors use 2,
authentication/keychain problems use 3, gateway/stream problems use 4, cancellation
uses 130. Network/SDK exception details are never printed. Terminal output strips
control sequences; `--json` represents text as JSON escapes.

## Development and standalone packaging

```sh
python -m pip install -r requirements-build.txt -c constraints.txt
python -m pytest -q
python scripts/build_cli.py
python scripts/smoke_cli.py
```

Direct dependencies and shared constraints are pinned, including platform-only
constraints. PR tests and standalone/release builds use the same inputs. The build
includes the active OS keychain backend and certifi certificate bundle. Both `swa`
and `swahilipro` aliases remain standalone; users do not need Python or Node.
Version stamping in swa_cli.py remains unchanged. No release/publication workflow
was triggered by this implementation.

Validation covers the existing runtime, challenge binding and poll spacing,
expiry/denial/cancellation, origin isolation, refresh recovery and process locking,
keychain failure, redaction, redirect rejection, split UTF-8, malformed/oversized
streams, duplicate/interrupted requests, and account-bound status recovery.
`tests/fixtures/gateway-v1.json` records the matching backend commit/contract.

Local validation builds and smoke-tests Linux binaries. Actual interactive OS
keychain behavior, Windows/macOS packaged execution, trusted HTTPS against the
staging deployment, and a funded exact-model turn still require platform/staging
validation. CI contains the four existing OS/architecture build targets. Mocked
HTTP tests make no Firebase, AWS or paid model calls. This is a draft integration,
not a completed coding agent or release parity claim.

Implementation references:
- https://keyring.readthedocs.io/en/stable/
- https://www.pyinstaller.org/en/stable/hooks.html
