# Dependency readiness

`GET /health` remains a cheap process-liveness response. `GET /readyz` reads the
configured database with `SELECT 1` through the existing AUTOCOMMIT read engine,
then sends Redis `PING` when `CACHE_ENABLED` is true. The maintained Compose
example uses `/readyz` for API health, so its existing dependent service condition
does not treat a listening HTTP process alone as dependency-ready.

The response has `status` (`ready` or `unavailable`) and `checks.database` and
`checks.cache`. Checks are `ok`, `unavailable`, or `not_checked`; disabled cache
is explicitly `disabled`. HTTP 200 requires database success and either cache
success or disabled cache. Other results return 503. Every response has
`Cache-Control: no-store`; each request rechecks dependencies without retaining
shared result state. A database failure skips the cache probe. Ordinary cache
operations may use the existing in-memory fallback, but configured Redis still
has to answer this stricter readiness probe.

The combined probe has a 1.5-second asynchronous cancellation budget and Redis
cleanup has a separate 0.25-second budget. These rely on cooperative driver
cancellation; they are not a hard wall-clock guarantee for a blocking or
cancellation-suppressing driver. Caller cancellation propagates after attempted
cleanup. Each probe returns its database connection and owns/closes only its
temporary Redis client. Cleanup failure also prevents a ready response.

The Redis URL removes only the demonstrated Cashews-specific `suppress` query
option. Redis database, TLS and transport options remain intact and are parsed
by Redis itself. Unsupported options and malformed addresses fail closed. The
route returns no connection URL, credentials, exception detail or traceback and
does not log underlying exception text. It uses existing configured bindings;
there is no model/provider request, memory write, schema mutation or retry queue.
After repairing a dependency, repeat the request to obtain a fresh result.

This probe does not validate migrations, the embedding schema, stored vectors,
worker progress, cache correctness, model availability, authenticated API calls
or memory-model compatibility. Existing startup and authentication controls
remain responsible for their own boundaries. The route is public like `/health`
and exposes only dependency status. No installed configuration or service is
changed by accepting this source. Deploying a Compose file and operating a real
store remain separate work.

## Source and verification

This adaptation starts from main
`4228047492cf66e5c6e52923161ce758c736c8d2` and preserves the readiness proposal
at retained originals `2d4964540f7fa6e626ed1bc8b586a80b29b9f368` and
`0d72ce69ae4d5880e363845e75b66d8b5266b19e`. Their broader local-model, embedding,
reconciliation, deployment and historical report changes are separate. Original
source pins and accepted revisions must remain distinct. No private history is
introduced into the public repository.

`tests/offline/test_readiness.py` exercises the actual registered application
through HTTPX ASGI transport without starting lifespan. It injects fictional
dependency objects and checks liveness, disabled cache, failures at acquisition,
query and cleanup, cancellation budgets, false PING responses, query-option
preservation through the real Redis constructor, recovery and concurrent calls.
The existing pytest fixture exclusion prevents these tests from opening a test
database. The Compose consumer is parsed and checked against the actual route.

With the locked dependencies and explicitly fictional app configuration prepared:

```sh
uv run python -m unittest discover -s tests/offline -p test_readiness.py -v
uv run pytest -o addopts='' tests/offline/test_readiness.py
uv run ruff check src/main.py tests/offline/test_readiness.py tests/conftest.py
```

The external source receipt contains the exact clean environment, isolation
profile, dependency/bootstrap hashes, dated test/lint results, unchanged failing
baseline and independent review. Application import needs the locked tokenizer
vocabulary files; the test preparation fetched the two public files by their
package-pinned hashes before network-denied execution. In this environment the
test bootstrap also skips urllib3's optional IPv6 bind-capability detection;
no listener or real dependency endpoint is required. Neither fixture success nor
source acceptance proves a live deployment or private Foundry adoption.
