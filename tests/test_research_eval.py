"""Research-validity tests for differential metrics and ground truth."""

from __future__ import annotations

from pathlib import Path

from agenticapi.config import Settings
from agenticapi.evaluation.fault_runner import case_touches
from agenticapi.evaluation.faults import all_faults, applicable_fault_ids, fault_by_id
from agenticapi.evaluation.ground_truth import (
    case_exercises_fault,
    differential_ground_truth,
)
from agenticapi.evaluation.manifest import build_run_manifest, write_sha256sums
from agenticapi.evaluation.metrics import summarize
from agenticapi.llm.provider import OllamaProvider, build_provider
from agenticapi.models import (
    APISpec,
    ExperimentConfig,
    OracleResult,
    Outcome,
    RequestStep,
    Technique,
    TestCase,
)
from agenticapi.spec.loader import load_spec


def _case(case_id: str, path: str = "/products/p1") -> TestCase:
    return TestCase(
        case_id=case_id,
        operation_id="get_product",
        technique=Technique.FUNCTIONAL,
        steps=[RequestStep(method="GET", path=path)],
    )


def _record(status: int, body: dict | None = None) -> dict:
    return {
        "case_id": "case",
        "steps": [{"index": 1, "status_code": status, "body": body}],
        "error": "",
    }


def test_differential_metrics_ignore_errors_and_invalid_tests() -> None:
    case_a = _case("a")
    case_b = _case("b")
    clean = [
        OracleResult(case_id="a", outcome=Outcome.PASS),
        OracleResult(case_id="b", outcome=Outcome.PASS),
    ]
    faults = {
        "F01": [
            OracleResult(case_id="a", outcome=Outcome.FAIL, failure_kind="status"),
            OracleResult(case_id="b", outcome=Outcome.ERROR),
        ],
        "F02": [
            OracleResult(case_id="a", outcome=Outcome.PASS),
            OracleResult(case_id="b", outcome=Outcome.INVALID_TEST),
        ],
    }
    metrics = summarize(
        clean,
        faults,
        eligible_fault_ids=["F01", "F02"],
        cases=[case_a, case_b],
    )
    assert metrics["detected_faults"] == ["F01"]
    assert metrics["fault_level_matrix"]["tp"] == 1
    assert metrics["fault_level_matrix"]["fn"] == 1
    assert metrics["case_pairs"]["errors"] == 1
    assert metrics["case_pairs"]["invalid"] == 1


def test_no_opportunity_is_reported_separately() -> None:
    case = _case("a")
    metrics = summarize(
        [OracleResult(case_id="a", outcome=Outcome.PASS)],
        {},
        eligible_fault_ids=["F06"],
        cases=[case],
    )
    assert metrics["faults_no_opportunity"] == 1
    assert metrics["fault_details"]["F06"]["no_opportunity"] is True
    assert metrics["fault_level_matrix"]["opportunity_faults"] == 0


def test_ground_truth_requires_clean_fault_difference() -> None:
    case = {
        "case_id": "c",
        "steps": [{"method": "GET", "path": "/products/p1"}],
    }
    clean = _record(200, {"price": 99.99, "name": "Widget", "stock": 1})
    fault = _record(200, {"price": "99.99", "name": "Widget", "stock": 1})
    assert differential_ground_truth(case, clean, fault, "F02") is True
    assert differential_ground_truth(case, clean, clean, "F02") is False
    assert differential_ground_truth(case, clean, _record(500), "F01") is True


def test_ground_truth_authz_and_idempotency_stimuli() -> None:
    authz = {
        "case_id": "authz",
        "steps": [{"method": "GET", "path": "/orders/o1", "auth": "user"}],
    }
    assert case_exercises_fault(authz, "F06") is True
    assert (
        differential_ground_truth(
            authz,
            _record(403),
            _record(200, {"id": "o1"}),
            "F06",
        )
        is True
    )

    idem = {
        "case_id": "idem",
        "steps": [
            {
                "method": "POST",
                "path": "/orders",
                "headers": {"Idempotency-Key": "same"},
            },
            {
                "method": "POST",
                "path": "/orders",
                "headers": {"Idempotency-Key": "same"},
            },
        ],
    }
    assert case_exercises_fault(idem, "F09") is True


def test_applicable_faults_and_template_selection() -> None:
    spec = load_spec("datasets/shop_openapi3.json")
    assert len(applicable_fault_ids(spec.operations)) == len(all_faults()) == 12
    case = _case("templated", path="/products/{product_id}")
    assert case_touches(case, fault_by_id("F01")) is True


def test_ollama_options_and_top_level_token_counts() -> None:
    import contextlib
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            seen.append(json.loads(self.rfile.read(length)))
            payload = json.dumps(
                {
                    "model": "qwen2.5:1.5b",
                    "message": {"role": "assistant", "content": "{}"},
                    "prompt_eval_count": 17,
                    "eval_count": 5,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:
            pass

    @contextlib.contextmanager
    def server():
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield httpd
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    with server() as httpd:
        provider = OllamaProvider(
            base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
            model="qwen2.5:1.5b",
            seed=7,
            num_predict=64,
        )
        response = provider.complete([{"role": "user", "content": "x"}])
    assert response.prompt_tokens == 17
    assert response.completion_tokens == 5
    assert seen[0]["options"]["seed"] == 7
    assert seen[0]["options"]["num_predict"] == 64


def test_build_provider_selects_ollama(tmp_path: Path) -> None:
    settings = Settings(
        root=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        datasets_dir=tmp_path / "datasets",
        configs_dir=tmp_path / "configs",
        llm_provider="ollama",
        llm_api_key="",
        llm_base_url="http://localhost:11434",
        llm_model="qwen2.5:1.5b",
        llm_timeout_seconds=5.0,
        llm_max_retries=0,
        input_price_per_million=None,
        output_price_per_million=None,
        default_base_url="http://127.0.0.1:8765",
        default_token="token-alice",
    )
    provider = build_provider(settings, seed=3)
    assert isinstance(provider, OllamaProvider)
    assert provider.seed == 3


def test_manifest_and_checksums(tmp_path: Path) -> None:
    settings = Settings(
        root=Path(__file__).resolve().parent.parent,
        artifacts_dir=tmp_path / "artifacts",
        datasets_dir=tmp_path / "datasets",
        configs_dir=tmp_path / "configs",
        llm_provider="ollama",
        llm_api_key="",
        llm_base_url="http://localhost:11434",
        llm_model="qwen2.5:1.5b",
        llm_timeout_seconds=5.0,
        llm_max_retries=0,
        input_price_per_million=None,
        output_price_per_million=None,
        default_base_url="http://127.0.0.1:8765",
        default_token="token-alice",
    )
    spec: APISpec = load_spec("datasets/shop_openapi3.json")
    manifest = build_run_manifest(
        settings,
        spec,
        ExperimentConfig(),
        ["C0_legacy"],
        [1],
    )
    assert len(manifest["dataset"]["sha256"]) == 64
    assert len(manifest["code"]["source_sha256"]) == 64
    assert manifest["dataset"]["operations"] == 15

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "a.json").write_text("{}", encoding="utf-8")
    target = write_sha256sums(run_dir)
    assert target.is_file()
    assert "a.json" in target.read_text(encoding="utf-8")
