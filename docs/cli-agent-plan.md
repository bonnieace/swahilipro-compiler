# SwahiliPro CLI coding-agent implementation plan

Status: proposed; documentation only.
Date: 2026-09-30.
Revised 2026-10-01 for Firebase Authentication, Firestore, and Next.js client authorization.
Inspected main commit: 613441bfe21e10c9b0b6f686ef7fa918150e5cd4.
Companion architecture: https://github.com/bonnieace/swahilipro_web/blob/docs/agent-platform-plan/docs/agent-platform-plan.md

## Outcome

Extend the existing standalone swa CLI with browser login, shared account credits, streamed chat, and a local coding-agent loop. Use the Next.js gateway for every paid model call and Firebase Authentication for website identity. Keep the Python runtime usable offline without an account. Build the agent once in Python and expose a structured process interface that the VS Code extension can later consume.

This delivers familiar coding-agent workflows; it does not assume parity with Codex or Claude Code without task-based evaluation.

## Verified repository findings

| Source | Existing behavior and implication |
| --- | --- |
| swa_cli.py | argparse CLI; no arguments opens REPL; supports repl, a file or stdin, version/help aliases, and specially dispatched check. Add commands without breaking file dispatch. VERSION is stamped by release automation. |
| swahilipro.py | Public run/check API forwards to compat_v2; preserve this API for existing consumers. |
| compat_v2.py | check parses without execution. run executes against module-global GLOBAL_ENV. Built-ins include input, file execution via endesha, and terminal clearing through os.system. Running generated code is not sandboxed. |
| shell.py | Legacy entry point delegates to the REPL; keep it working. |
| tests/test_cli.py | Existing tests cover aliases, help/version, file errors, silent checks, diagnostics, and banner layout. |
| tests/test_v2_syntax.py | Covers v2 and v1 compatibility; resets global environment between tests. |
| .github/workflows/standalone-cli.yml | Python 3.11, pytest, and PyInstaller; builds both swa and swahilipro aliases on Windows, Linux, macOS Intel/ARM. |
| .github/workflows/release-resilient.yml | Builds platform binaries and packages extension VSIX files by cloning extension master. Supports dry-run and then release/Marketplace publication. |
| .github/workflows/marketplace-publish.yml | Existing separate Marketplace publishing/retry flow. Preserve its publication responsibilities. |
| Repository tree | No agent package, auth/network client, dependency manifest/lock, or AGENTS.md. Tracked __pycache__ artifacts exist. |

This is source inspection; no runtime tests or live authentication/model requests were executed for this planning change.

## Ownership and architecture

- Firebase Auth owns website identities; Next.js owns the explicit native-client login-attempt, grant and token lifecycle defined by the web plan.
- Next.js owns account permissions, model policies, credit reservation/settlement, and Bedrock adapters.
- The CLI owns terminal interaction, local context, approvals, file operations, process execution, and session history.
- The extension will own its UI, SecretStorage, and editor-specific approval surfaces, using the same packaged agent engine.
- Do not ship AWS credentials, Firebase Admin credentials, database connections, or an OAuth client secret in the binary. No direct Bedrock or credit-table writes in the initial CLI.

Add a swa_agent Python package with these boundaries:

| Proposed module | Responsibility |
| --- | --- |
| commands.py | login/logout/whoami/credits/models/chat/sessions dispatch |
| config.py | Trusted API/auth origins, public client ID, user-level settings |
| auth.py / credentials.py | Challenge-bound browser approval, refresh coordination, OS credential storage |
| gateway.py / events.py | Versioned HTTP/SSE contract, request status, stream validation |
| engine.py | Bounded model/tool loop, cancellation, step and usage limits |
| context.py | Workspace discovery, selected files, ignore rules, context budget |
| tools/ | Read/list/search, patch proposals/application, approved process execution |
| policy.py | Workspace boundaries and explicit authorization decisions |
| sessions.py | Local history, operation journal, resume, deletion |
| terminal.py | Human-readable streaming, diffs, prompts, errors |
| protocol.py | Versioned JSON-lines stdin/stdout interface for a future extension |
| language.py | Versioned SwahiliPro v2 guidance and check integration |

Keep these modules independent of terminal input/printing. Lazy-load agent dependencies so existing runtime commands do not require an available keychain, login, or network.

## CLI contract and compatibility

| Command | Intended behavior |
| --- | --- |
| swa / swa repl | Existing offline REPL, unchanged |
| swa file.swa / swa - / swa check file.swa | Existing execution/stdin/check behavior |
| swa login | Explicit browser-based login; never triggered by installation |
| swa logout | Clear local credentials and attempt supported remote revocation |
| swa whoami | Show authenticated identity and login state |
| swa credits | Show server-authoritative available/reserved balance |
| swa models | Show permitted models and capabilities from the gateway |
| swa chat | Interactive coding session rooted at the chosen workspace |
| swa chat --model ID | Select an allowed model without hard-coding provider names |
| swa chat --resume ID | Resume local history after validating workspace/account |
| swa chat --prompt TEXT --json | Noninteractive stream; no implicit mutation approvals |
| swa sessions list/delete ID | Manage local conversations |
| swa agent --stdio | Future extension-hosted protocol, separate from terminal chat |

Preserve swahilipro as an alias, existing help/version flags, stdin handling, and silent successful check output. Recognize exact new command names before falling back to file execution. Document ./chat (or an absolute path) for a source file named like a command and add swa run PATH as an unambiguous file entry point. Do not route ordinary files through authentication.

Keep existing runtime exit codes. Define and document new agent exit codes for authentication, gateway/quota, approval-required, and cancellation without changing runtime semantics. JSON/stdin protocol stdout contains only structured records; banners and diagnostics must not corrupt it.

## Authentication and credentials

Website sign-in uses Firebase Authentication. Native clients use SwahiliPro credentials issued by Next.js after explicit browser approval; Firebase is not treated as an OAuth authorization server.

Implement the shared web-plan protocol:
1. Generate a random verifier; send S256 challenge and public client type/label to /api/v1/auth/client/start.
2. Retain returned high-entropy polling secret in memory and open the website verification URL. For headless terminals show that URL and the confirmation phrase/code; no callback listener or separate device-OAuth capability is required.
3. User signs into Firebase in the browser and explicitly approves the matching client request.
4. Poll at the advertised bounded interval; final completion presents polling secret and verifier. The server atomically consumes the attempt and returns application access/refresh credentials.
5. Store rotating refresh credential in the OS keychain. Use short-lived access tokens for Next.js product APIs. No Firebase password, service-account key, Firebase refresh token or AWS credential belongs in the CLI.

Treat this as an application authorization protocol with versioned fixtures, not standard OAuth/PKCE compliance. The challenge binds token retrieval to the initiating client. Test denial, expiry, stolen URL, wrong verifier, repeated completion, rate limiting, and cancellation. No access/refresh secret appears in a URL or process arguments.

Use maintained cryptographic/random and HTTP primitives; pin dependencies. Configured API/auth origins are trusted user-level settings only; repository files cannot redirect tokens. Enforce HTTPS and origin constraints on credential-bearing requests.

Use Windows Credential Manager, macOS Keychain or an available Linux secret service via a tested adapter. Reject silent plaintext fallback; explicitly opt into a restricted-permission fallback only if needed. Isolate credentials by trusted origin and account. Serialize refresh across processes and follow the server's tested rotation/lost-response policy; replay is not blindly retried.

Portal per-device revocation applies to application grants. Firebase account disable/delete/sign-out-everywhere is coordinated with grant revocation on the server; Firebase refresh revocation alone does not invalidate application tokens. CLI logout clears local credentials and attempts grant revocation; explain when offline revocation is unconfirmed.

The CLI never talks directly to Firestore or changes balances. Backend Firebase Admin verification is for Firebase website credentials; application client tokens use their own server validation. Maintain clear credential types in the contract.

## Gateway and credits

Consume GET /api/v1/me, /credits, /models, POST /api/v1/inference, and GET /api/v1/requests/:id. Treat the web repository's published OpenAPI/event fixtures as the contract source; check in compatible fixtures with a schema version rather than copying business logic.

Parse streamed request.started, text.delta, tool_call.delta, usage, request.completed, and request.failed events incrementally. Support split UTF-8, fragmented tool arguments, unknown compatible events, frame limits, timeouts, and malformed-stream errors. Validate complete tool arguments only after assembly; never execute partial deltas.

Generate and durably record an idempotency key per paid model turn before sending it. Reuse that key when resolving uncertain transport outcomes. If disconnected before receiving a request ID, reuse the same key/payload to obtain the existing request rather than initiating new inference. After a known ID exists, query its status. Do not assume the server stores replayable output: mark missing output as incomplete and ask before a fresh paid turn.

Show server-reported usage and remaining credits. Local estimates are advisory. Handle insufficient credits, 429/backoff, disabled models, incompatible API versions, expired sessions, and ambiguous provider outcomes without retry storms. Each agent tool cycle can incur another model call; stop at configured turn, time, output, and cost limits.

## Local tools and approval policy

Start with list/read/search and patch proposals, then approved writes and process execution. All file tools use a selected workspace root, canonical paths, symlink-aware containment checks, file/byte limits, and ignore rules. Exclude .git internals, credential files, private keys, common secret files, and large/binary outputs by default. Respect .gitignore and an explicit agent ignore file. Display which context is sent; do not automatically upload the entire repository.

Read-only tools may run within the approved workspace. Before writing, show a diff and check the current file hash against the proposed base. Refuse stale edits rather than overwriting user changes. Apply writes atomically where possible, journal affected paths, and make undo conditional on unchanged post-edit hashes. Never use git reset or blanket checkout to undo agent work.

Before executing commands, show command/arguments, cwd, and expected side effects. Default to argv-based subprocesses; shell execution needs explicit approval. Bound execution time/output, manage process groups for cancellation, avoid inherited credentials, and never auto-install packages or run repository hooks. Workspace path restrictions on file tools do not sandbox an arbitrary process: document this distinction and keep execution explicitly approved.

Treat repository text, tool output, and model instructions as untrusted context; they cannot change authorization policy or grant approvals. No automatic git commit/push, deletion, or external action. Noninteractive mode returns approval_required for unapproved mutation/commands. Session-level permissions must be explicit and scoped.

## SwahiliPro validation

Provide concise bundled v2 syntax guidance derived from README and syntax tests, including end-exclusive ranges, function syntax, and the v1 migration boundary. Keep general repository assistance possible; load language guidance when relevant.

Use swahilipro.check for syntax-only validation of proposed .swa code; label this as syntax checking, not proof of correctness. Run checks with resource bounds for large/untrusted input.

Execute approved generated programs in a separate process using the packaged CLI, with a timeout and bounded output. Do not use shared GLOBAL_ENV for agent execution: it persists across calls, and programs may read files, request input, or loop indefinitely. Treat running .swa code as command execution requiring approval. Preserve normal REPL state behavior.

## Shared extension engine

Proposed integration: the extension spawns its bundled matching swa binary with agent --stdio rather than reimplementing the tool loop in TypeScript. This fits the existing runtime bundling pipeline but remains subject to extension-repository inspection.

Define version/capability handshake, request IDs, session start/resume, prompt, streaming events, tool proposal, approval response, cancellation, and shutdown. Bind every approval to the exact tool call and arguments; reject stale/duplicate approvals. Keep localhost network ports closed for this protocol.

The extension should own extension credentials in SecretStorage; pass short-lived credentials through private process IPC, never command-line arguments or logs. The engine requests token renewal from the host as needed; it must not persist host credentials. CLI mode uses its own keychain adapter. Both represent the same web account but may have separate revocable grants.

If the host dies, stop pending tools/model calls where possible. Restart/resume must never rerun an uncertain command automatically. Test editor dirty-buffer conflicts when integrating the extension.

## History and recovery

Store sessions in per-user application data directories, outside repositories, with restricted permissions, schema versions, and atomic writes. Record workspace identity, account/API origin, model, request IDs/idempotency keys, approvals, and tool outcomes. Tokens never belong in history. Explain local source-content retention, offer history disable/delete controls, and keep telemetry off unless explicitly introduced.

On resume, recheck workspace hashes, session ownership, authentication, and current model availability. Uncertain command outcomes require user review. Never infer an unexecuted operation from a missing completion event.

## Packaging and release changes

Add pyproject.toml and pinned dependency/build inputs for networking, authorization protocol support, credential storage, and terminal rendering after compatibility tests. Retain standalone distribution: users should not need Python, pip, or Node. Add PyInstaller hooks/spec configuration for certificates, keychain backends, resources, and dynamically imported dependencies.

Update tests.yml, standalone-cli.yml, and release-resilient.yml consistently so all install the same dependency set. Test packaged binaries, not only Python source, on the existing Linux x64, Windows x64, macOS x64/ARM targets. Measure startup and artifact-size changes and keep offline runtime commands fast.

Preserve release version stamping or update its exact regex alongside any move of VERSION. Pin the extension commit used for a release and record compiler, extension, API, and protocol versions; the current moving master checkout is unsuitable for reproducible cross-repo agent releases. Add checksum manifests and verify artifacts before packaging. Keep release dry-run as the validation path; this planning work does not trigger publication or modify Marketplace credentials.

Remove tracked bytecode and add ignore rules as a scoped housekeeping change. Do not conflate that with interpreter rewrites.

## Ordered implementation slices

1. **Dispatch and package foundation:** manifest/pins, lazy-loaded package, compatibility dispatch, protocol/schema fixtures, and fake gateway. Acceptance: all existing runtime tests pass and file/check/REPL work without network or auth dependencies being initialized.
2. **Accounts and read APIs:** gated on the web Firebase/client-grant implementation; login/logout/whoami/credits/models with OS credential adapters. Acceptance: cancellation, wrong verifier, stolen verification URL, replay, expiry, refresh races, revoked grant, unavailable keychain, and secret-redaction tests.
3. **Streamed read-only chat:** gateway adapter, context limits, terminal UI, idempotency journal, and cancellation. Acceptance: fragmented streams, disconnect before/after request ID, quota errors, and restart do not cause a duplicate paid call.
4. **Local coding tools:** read/search, diff review, atomic patches, approved commands, syntax validation. Acceptance: path traversal/symlink escape, ignored secrets, stale files, denied tool calls, command timeout, and user edits are handled correctly.
5. **Shared engine protocol and resume:** agent --stdio, host token/approval adapters, persisted sessions, and capability handshake. Acceptance: fake extension host can stream, approve/deny, cancel, restart, and detect version mismatch without automatic tool replay.
6. **Cross-platform beta release:** all workflows use pinned dependencies; packaged smoke tests and resilient release dry-run; verify one funded staging account with small explicit limits. Evaluate real tasks before expanding access.

Backend dependencies: web accounts/client authorization must precede real login; ledger/model catalog and inference streaming must precede paid chat. Compiler dispatch, fixtures, tools, and protocol can be developed against a fake gateway meanwhile.

## Meaningful validation

- Retain existing CLI and syntax regression suites.
- Add deterministic fake-auth/gateway tests; CI never needs AWS credentials or paid requests.
- Test actual packaged HTTPS certificate handling and credential adapters on supported OSes; document runner limitations where interactive keychains cannot be exercised.
- Evaluate tasks: explain a repository file, fix a broken .swa program, modify a small multi-file project, run an approved test, recover from a failed tool, and preserve a pre-existing dirty working tree.
- Measure completion rate, unnecessary calls, cost per completed task, correct approval behavior, latency, and cancellation/recovery. Start with one verified model; compare additional models only after tool and accounting behavior passes.
- No production deployment or release is implied by approval of this plan.

## Open implementation decisions

Confirm the public API/auth origins, client-start/approval/completion schemas, polling/expiry and rotation semantics, permission/grant mapping, server stream/recovery contract, credit units, supported model list, keychain fallback policy, and extension protocol capabilities. The web plan owns Firebase/Coolify operations and financial rules; this repository owns the local agent and standalone distribution.
