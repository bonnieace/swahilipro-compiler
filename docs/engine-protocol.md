# Local tools and shared engine protocol v1

This extends the CLI account/chat preview with local tools and a private stdio
interface for the future VS Code host. The backend still advertises text-only
inference. `autonomousToolLoop` is false: model output is displayed as text and never
interpreted as executable tool requests. A trusted CLI or editor host explicitly
requests each tool. Native model tool calling and autonomous multi-step orchestration
remain a separate backend/engine integration.

## CLI tools

Tools do not require login. Choose an absolute workspace and use relative tool paths:

```sh
swa tool --workspace /absolute/repo list
swa tool --workspace /absolute/repo read src/example.swa
swa tool --workspace /absolute/repo search 'andika'
swa tool --workspace /absolute/repo edit src/example.swa --base-hash HASH_FROM_READ --text-file /tmp/proposed.swa
swa tool --workspace /absolute/repo execute --cwd . --timeout 30 -- /absolute/path/to/python -m pytest
swa tool --workspace /absolute/repo operation OPERATION_ID
swa tool --workspace /absolute/repo undo OPERATION_ID
```

`--json` belongs before the tool name. Reads/list/search need no mutation approval.
Edits show the exact diff, workspace, target and approval hash. Execution shows the
exact argv, cwd and timeout. An interactive terminal must type `yes`; JSON or piped
execution returns approval_required_or_denied (exit 5) instead of silently approving.
There is no `--yes` bypass. CLI proposals are supplied explicitly with --text-file;
chat does not discover or execute tools from model text.

Use `--base-hash absent` only to create a missing file under an existing directory.
Hash mismatch refuses a write, including changes during the approval dialog.
Existing-file undo is another reviewed edit and only succeeds while the file matches
the recorded post-edit hash. Creation undo, deletion and renaming are not provided;
there is no git reset/checkout cleanup. Atomic replacement preserves ordinary mode
bits but does not preserve extended attributes/ACLs.

## Workspace policy and limits

Paths must remain under the selected canonical root. Traversal, symlinks, junctions,
hardlinked files and special files are refused. Git internals, common credential
files, private-key suffixes, environment files, node_modules and virtual environments
are excluded. Root/nested .gitignore and .swaignore rules apply; nested rules cannot
reopen an excluded ancestor. These exclusions cannot identify every secret, so the
host must display which context will be sent. There is no automatic repository upload.

UTF-8 text files are limited to 32 KiB, directory traversal to 2,000 entries, and
literal search to 512 KB of text and 100 matches. Binary/oversized files are skipped
by search and rejected by explicit reads. `.swa` edit proposals receive bounded
parse-only validation on POSIX, never program execution. A successful syntax check
is not proof of behavior; a failed check remains visible in the review.

POSIX reads/writes traverse directory descriptors without following symlinks.
Disk edits recheck the base hash before replacement and serialize cooperating engine
writers. A concurrent external writer can still race the final comparison/rename;
this is not a filesystem-wide transaction. Editor mode instead relies on document
version/hash checks and WorkspaceEdit, without any engine disk write.

Native disk mutation and command execution are currently enabled only on POSIX
(Linux/macOS). Windows exposes host-managed edits and reads; the handshake accurately
disables its native mutation/execution adapter pending platform implementation and QA.
The editor host must not enable buttons based solely on a runtime version string.

## Command execution

Execution requires an absolute executable and explicit argv; shell=False is always
used. An explicitly approved shell executable with arguments is still arbitrary
command execution. The cwd is validated under the workspace, but the subprocess
can read/write outside it and access the network. This is not a security sandbox.

The child receives a small environment (system PATH and locale), no inherited API
credentials, no stdin and no inherited descriptors. Timeout is 1–60 seconds; combined
stdout/stderr is capped at 32 KiB. POSIX process groups are terminated on cancellation,
timeout, excessive output or parent completion. Programs deliberately escaping the
process group are outside that cleanup guarantee; only approve commands you trust.
Commands are never automatically retried after interruption.

## Protocol framing and lifecycle

Launch the matching packaged binary with `swa agent --stdio`, no shell, no token in
argv. The engine writes one hello frame before accepting initialization:

```json
{"v":1,"type":"hello","protocol":1,"runtimeVersion":"...","capabilities":["initialize","tool","prompt","request.status","reply","cancel","shutdown"]}
```

The trusted host checks protocol/capabilities and workspace trust before sending
credentials or source. Frames are UTF-8 newline-delimited JSON, max 256 KiB each.
Stdout is protocol-only. IDs are unique per process (1–80 letters/digits/_/-); the
process accepts at most 10,000 IDs. There is one active operation, with concurrent
reply/cancel/shutdown control messages. Oversized/truncated frames end the process.
Unknown versions/methods and duplicate IDs fail explicitly.

```json
{"v":1,"id":"init","method":"initialize","params":{"workspace":"/absolute/repo","mode":"host","apiOrigin":"https://YOUR-HOST","uid":"FIREBASE_UID"}}
{"v":1,"id":"read1","method":"tool","params":{"name":"read","arguments":{"path":"src/example.swa"}}}
```

Initialization is once per process. `mode: host` delegates editor reads/edits;
`mode: disk` uses the CLI adapter. Omitting both apiOrigin and uid creates a tools-only
session. apiOrigin must be HTTPS. The host chooses these values from trusted user
settings; repository content must never control them. Account/workspace switches
require cancellation and a fresh process. The initialization result gives exact
capability booleans. Host mode currently disables native command execution and disk
search; use explicit host reads until editor-aware search/execution adapters exist.

Tool arguments are exact (extra fields are rejected):

| Tool | Arguments |
| --- | --- |
| list | `{}` |
| read | `{path}` |
| search | `{query}` (disk mode) |
| edit | `{path, text, baseHash}` (`null` for a missing file) |
| undo | `{operationId}` (existing-file disk edits) |
| execute | `{argv, cwd, timeout}` (POSIX disk mode) |
| operation | `{operationId}` (safe journal metadata only) |

Responses are `{v,id,type:result,result}` or `{v,id,type:error,error}`. Events include
id for the initiating operation. Errors contain stable codes, never SDK exceptions,
request headers or host credential payloads.

## Host requests, editor versions and approval binding

During a tool operation, the worker emits an event and waits while stdin continues
accepting replies/cancellation:

```json
{"v":1,"id":"read1","type":"event","event":"host.request","kind":"read","operationRequestId":"read1","callId":"RANDOM_NONCE","binding":"SHA256","payload":{"path":"src/example.swa","allowMissing":false}}
{"v":1,"id":"reply1","method":"reply","params":{"callId":"RANDOM_NONCE","binding":"SHA256","result":{"exists":true,"text":"current unsaved text","version":7}}}
```

`binding` hashes the complete host-request body including operationRequestId. A call
ID is consumed once. Wrong/late/duplicated replies fail. The host must correlate the
request with the active workspace/operation; repository/model text cannot send replies.

For an edit, the engine reads the current host snapshot, verifies baseHash, generates
a diff and emits `kind: approval` with a `proposal`. The proposal includes random
operationId, workspace, path, base hash, document version, new text/hash, diff and
optional syntax result. Reply `result: {approved:true, approvalHash:...}` only after
showing and approving that exact proposal; denial can return `{approved:false}`.
The approval hash is over the complete proposal excluding the hash field itself.

After approval, the engine reads again and refuses changed text/version. It then
emits `kind: apply` with the approved proposal. The host must recheck version/hash
immediately before a WorkspaceEdit, preserve normal editor undo, and not save dirty
buffers implicitly. Return `{applied:true,hash:"ACTUAL_POST_EDIT_SHA256"}` only after
confirming application; otherwise return `{applied:false}`. The engine never falls
back to a disk write. An uncertain apply result remains uncertain in its journal.

Approval waits expire after 120 seconds; other host requests after 30 seconds.
EOF, Stop or shutdown cancels outstanding work and invalidates pending approvals.
No approval survives process restart. Host-managed undo stays in VS Code.

## Host-owned credentials and streamed prompts

`prompt` takes exactly `{messages,model,maxOutputTokens}`, matching the text-only
backend contract. The engine requests `kind: credential` with origin/uid. Reply over
private stdin with `{accessToken,expiresIn}` (120–900 seconds remaining). The host
owns SecretStorage, refresh rotation and renewal. Refresh credentials are never
accepted, persisted or echoed by this engine. It checks /me against initialized uid
before starting a paid request.

Gateway events are wrapped as `{v,id,type:event,event:gateway,data:...}`. Request
receipts and idempotency protection are shared with CLI chat. `request.status` takes
`{requestId}` and only performs account-checked GET recovery. No response text or
conversation transcript is persisted. The host maintains chat history/context.
Cancellation uses `{method:cancel,params:{requestId:"ACTIVE_PROTOCOL_ID"}}`; it cannot
promise a refund. While an HTTP read is blocked, cancellation may take up to the
30-second transport timeout. Shutdown waits up to 35 seconds for the worker. The
host should stop accepting new actions immediately and enforce its own process
shutdown deadline. `shutdown`/EOF have no automatic resume/replay semantics.

## Operation journal

Before any edit/command side effect, a protected per-user workspace journal records
pending state and approval hash. Successful disk edits retain the original text
(base64 is encoding, not encryption) to support conditional undo. Host edits retain
metadata only; command output/argv are not persisted. Journal directory is beneath
the existing user data root under `operations/SHA256(canonical workspace)`.

`operation` reports state, hashes and requiresReview, without exposing backup text.
A crash can leave pending/unknown even when a side effect happened. Inspect the file
or command outcome; the engine never automatically replays an uncertain operation.
Deleting a journal does not undo a file or command. Backups may contain source code;
remove resolved journals when no longer needed. Session transcript resume/deletion
UI is not included in this phase.

## Verification and rollout

Tests exercise traversal, symlink/parent replacement, ignored/secret files, stale
versions, denial, mutated approval payloads, conditional undo, unknown journals,
clean command environment, timeout/output/cancel/group cleanup, host disconnect,
malformed frames, account mismatch and secret-free prompt streaming. Tests and
packaged host smoke checks need no cloud credentials or paid calls.

`scripts/smoke_engine.py` drives the real packaged stdio interface for both aliases,
including an unsaved host buffer read. The four-platform CI build runs this after
existing compiler/account smoke tests. Local builds/tests validate Linux; Windows
and macOS CI/runtime behavior and real VS Code WorkspaceEdit/SecretStorage integration
remain deployment gates. No release/Marketplace publication is implied.

The CLI account origin defaults to https://swahilipro.com when no user configuration
exists. `swa configure --api-origin https://YOUR-STAGING-HOST` still selects a
user-owned override; malformed existing settings are never silently ignored.
