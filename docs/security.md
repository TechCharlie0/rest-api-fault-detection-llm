# Security

## Scope

This is a local research prototype. It is not hardened for multi-tenant or
production use. The security goal is to keep experiments on loopback mock APIs and
to prevent accidental credential leakage into prompts, logs, artifacts, or generated
code.

## Controls

### Network locality

- `security.assert_safe_base_url` accepts only `http`/`https` URLs whose hostname is
  loopback (`localhost`, `127.0.0.1`, `::1`) or an IP in the loopback range.
- `ExecutionEngine` independently rejects non-loopback base URLs.
- HTTP requests disable redirects (`allow_redirects=False`) so a mock response
  cannot redirect execution to a non-loopback destination.
- No dataset points at a public API. The experiment uses only the local mock shop.
- There is no crawler or external discovery component.

### Secrets

- `.env` is git-ignored; `.env.example` contains placeholders only.
- The LLM key is read from `AGENTICAPI_LLM_API_KEY`, never from source.
- `security.redact` removes bearer tokens, API keys, passwords, and secret-like
  values before traces/errors are written.
- `scripts/check_secrets.py` scans source, tests, docs, configs, and scripts for
  common credential patterns. It reports no findings for the current tree.
- `LLMGateway` records token/cost metadata but not the API key.

### Generated code

`code_renderer.py` creates standalone pytest artifacts. Before an artifact is
counted as valid:

- it must parse as Python (`ast.parse`);
- only an allowlist of imports is permitted (`requests`, `json`, `pytest`,
  `jsonschema`, `base64`, `uuid`, `time`, `os`, `agenticapi`, `__future__`);
- dangerous calls such as `eval`, `exec`, `compile`, `open`, `__import__`,
  `os.system`, `os.popen`, `subprocess.*`, and `socket.socket` are rejected;
- literal URLs are checked for loopback hosts.

The artifacts are not executed by the orchestrator. Test cases are executed through
the structured `ExecutionEngine`, which avoids running generated source as a shell
or Python process. Tests compile the rendered files and run the policy check.

### Local admin surface

The mock API exposes `/__admin/reset`, `/__admin/fault`, and `/__admin/state` only
on the loopback server. They have no authentication. This is intentional for the
research harness but would be unacceptable in a deployed service.

## Verification

```bash
. .venv/bin/activate
ruff check agenticapi tests
mypy agenticapi
pytest -q
python scripts/check_secrets.py
```

Current observed results: ruff clean, mypy clean, 51 tests passed, secret scan clean.

## Known gaps

- No OS-level sandbox or container isolation.
- No dependency vulnerability audit (`pip-audit` was not installed or run).
- Static mock tokens (`token-alice`, `token-admin`) are not secrets and should not
  be reused outside the mock.
- Prompt-injection defense is limited to data framing, bounded inputs, JSON schema
  validation, and loopback-only execution. A malicious API document could still
  steer an LLM; results must be reviewed.
- No TLS, rate limiting, or authentication on admin endpoints.
- The checker is pattern-based and is not a substitute for a dedicated secret
  scanner.
