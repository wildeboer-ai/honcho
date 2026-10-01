# Retained Honcho source and dormant historical operations

Matt’s September 30 decisions close the remaining private-history and unfinished
deployment choices without selecting an account, deployment, model or runtime.

`matt/preserve-worktree-20260808` at
`0d72ce69ae4d5880e363845e75b66d8b5266b19e` is retained as a complete, verified,
private Rig Git bundle. Its seven vector-reconciliation JSON reports remain opaque
historical private metadata; they are not current retrieval evidence or test data.
That original is never joined into main. PR33 already recovered the shared
Ollama embedding/reasoning and private, bounded reconciliation producer. PR32’s
bounded readonly readiness and current caller tests remain authoritative.

The remaining neutral source restores `LLM_LOCAL_ONLY` and
`LLM_OLLAMA_BASE_URL`, Ollama-prefixed model names, and the workspace prompt’s
instruction to answer directly when the exact answer is already in context.
Global local-only refusal supplements the existing lane guards, endpoint,
credential, fallback, proxy and redirect restrictions. It also suppresses the
existing Langfuse observation hooks. Defaults do not enable this policy or start
an operation; callers must explicitly configure their selected model routes.
The Compose example also restores the summary model route; it requires an explicit
`HONCHO_LOCAL_SUMMARY_MODEL` selection instead of inventing an installed model.
The policy concerns model routing and trace export, not an assertion that every
other application subsystem is offline.

The direct `OllamaBackend(base_url=...)` preserves the separate native `/api/chat`
adapter: structured output, options, native/whole-message JSON tool calls, text
streaming and token usage. It owns a no-proxy/no-redirect HTTP client and requires
an approved local URL; close it with `await backend.aclose()`. Injected transports
are trusted caller dependencies. The registry continues its already accepted
OpenAI-compatible Ollama route, as the native donor did; this direct adapter is
not silently selected there. Required-tool choice and native tool streaming
explicitly refuse. Partial/error completion envelopes, unrequested tool calls and
malformed arguments refuse; a truncated stream cannot report completion. The
[Ollama chat contract](https://docs.ollama.com/api/chat) supplies the explicit
completion flag. No actual
model/runtime compatibility was exercised by the fictional HTTP tests.

`continuity/loawbot/125261b525602a6b/dirty-worktree-001/combined` at
`e9b03ccf001fe65404fb1fb5b08413ea421e5a8b` retains its native history.
Its Cloudflare/Vercel helpers remain dormant historical scaffolds: absent worker,
handler and requirements artifacts, ignored target/environment arguments, an
installing/broken TOML writer and unbound deployment accounts do not constitute
an executable deployment contract. They are not imported or copied into the
current runtime. No guessed entrypoint, credentials, account or production
configuration replaces those missing inputs.

The backup Compose variant’s distinct loopback ports, log rotation, labels and
resource reservations remain historical configuration choices (API/deriver
512M limits and 256M reservations, database 1024M/512M, Redis 256M/128M;
10m/three-file JSON logs). Its automatic exporter network, sample credentials,
trust authentication and weaker health checks are not current defaults. Current
opt-in dev-tools and PR32/33 configuration remain in place. The additive
`.dockerignore` change retains VCS/environment/cache/build exclusions while
preserving accepted rules and excluding generated private reports. The donor’s
`# test` comment is not a runtime capability.

The older Langfuse helper is adapted to the installed dependency’s v3 observation
interfaces. `get_langfuse_client`, `langfuse`, `trace_llm_call` and `trace_span`
require a caller-owned client and `enabled=True`; without that admission they
perform no SDK/configuration/credential discovery or trace export. There is no
global identity cache. Local-only policy suppresses them even with admission.
The caller remains responsible for destination, credentials, data authority and
SDK lifecycle. Completed LLM records end their child generation and parent span;
span contexts use the selected client’s managed observation. These interfaces
are source support, not automatic application instrumentation or live-provider
qualification.

Validation uses the real maintained callers with fictional HTTP, settings,
observation and SQL fixtures under denied network/home/store/process access.
No deployment, provider/model call, private report read, database/cache service,
install or credential operation is performed. Existing source reviews are reused;
original-ref retirement is a separate lead action after source and custody checks.
