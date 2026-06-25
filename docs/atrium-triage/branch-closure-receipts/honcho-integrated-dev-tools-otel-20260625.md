# Honcho dev-tools OTEL branch closure receipt

Date: 2026-06-25

Source branch:

- `origin/machine/LOAWs-Mini-2-dev-tools-otel-2026-06-15`

Disposition: integrated into `main` through `lawfirm/integrate/honcho-dev-tools-otel`.

Integrated capability:

- Added opt-in `DEV_TOOLS_*` / `[dev_tools]` configuration for local observability integrations.
- Added `src.dev_tools` with guarded setup for OTLP tracing, Loki logging, and Vault access.
- Added API and deriver startup hooks with distinct service names: `honcho-api` and `honcho-deriver`.
- Added OpenTelemetry instrumentation dependencies matched to the existing OpenTelemetry 1.41.x lock set.
- Added Loki and Vault dependencies: `python-json-logger`, `python-logging-loki`, and `hvac`.
- Added focused tests for disabled startup behavior, enabled setup fan-out, and Vault token resolution.
- Updated `.env.template` and `config.toml.example` with the new controls.

Source branch compatibility handling:

- The source branch enabled Jaeger/Loki defaults too aggressively for production startup. This integration keeps all dev-tools behavior disabled unless `DEV_TOOLS_ENABLED=true` and the specific sub-toggle is enabled.
- The source branch rewrote `.github/workflows/docker-build.yml` from the current GHCR/provenance flow to a Docker Hub/Trivy flow. That was not replayed because it changes release infrastructure rather than runtime dev-tools capability.
- The source branch changed the Docker base image and removed current Dockerfile behavior. That was not replayed; the runtime capability is available through the Python dependency set and opt-in settings.
- The source branch commits are preserved in repository history by an `ours` ancestry merge before remote branch deletion.

Validation:

- `uv run pytest tests/test_dev_tools.py`
- `uv run ruff check src/config.py src/dev_tools.py src/main.py src/deriver/__main__.py tests/conftest.py tests/test_dev_tools.py`
- `uv run basedpyright src/config.py src/dev_tools.py src/main.py src/deriver/__main__.py tests/conftest.py tests/test_dev_tools.py`
- `uv run basedpyright`
- `git diff --check`
