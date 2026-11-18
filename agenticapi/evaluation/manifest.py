"""Run provenance: hashes, environment, model configuration, and checksums."""

from __future__ import annotations

import hashlib
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from agenticapi.config import Settings
from agenticapi.models import APISpec, ExperimentConfig


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_hash(root: Path) -> str:
    """Hash the package source, including file names, without git metadata."""
    digest = hashlib.sha256()
    files = sorted((root / "agenticapi").rglob("*.py"))
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _memory_gb() -> float | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page_size / (1024**3), 2)
    except (AttributeError, OSError, ValueError):
        return None


def _ollama_metadata(settings: Settings) -> dict[str, Any]:
    if (settings.llm_provider or "").lower() != "ollama":
        return {}
    base_url = settings.llm_base_url.rstrip("/")
    if base_url == "https://api.openai.com/v1":
        base_url = "http://localhost:11434"
    metadata: dict[str, Any] = {}
    try:
        response = requests.get(f"{base_url}/api/version", timeout=2.0)
        if response.ok:
            metadata["version"] = response.json().get("version", "")
    except requests.RequestException:
        metadata["version"] = "unavailable"
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=2.0)
        if response.ok:
            models = response.json().get("models", [])
            metadata["available_models"] = sorted(
                str(model.get("name", "")) for model in models if isinstance(model, dict)
            )
    except requests.RequestException:
        pass
    return metadata


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    try:
        import jsonschema

        versions["jsonschema"] = str(jsonschema.__version__)
    except Exception:  # noqa: BLE001
        pass
    try:
        import requests as requests_module

        versions["requests"] = str(requests_module.__version__)
    except Exception:  # noqa: BLE001
        pass
    return versions


def build_run_manifest(
    settings: Settings,
    spec: APISpec,
    config: ExperimentConfig,
    conditions: list[str],
    seeds: list[int],
) -> dict[str, Any]:
    spec_path = Path(spec.source_path)
    if not spec_path.is_absolute():
        spec_path = settings.root / spec_path
    dataset_hash = sha256_file(spec_path) if spec_path.is_file() else ""
    prompt_hash = sha256_file(settings.root / "agenticapi/llm/prompts.py")
    schema_hash = sha256_file(settings.root / "agenticapi/llm/schemas.py")
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "code": {
            "source_sha256": source_tree_hash(settings.root),
            "source_root": str(settings.root),
        },
        "dataset": {
            "path": str(spec_path),
            "sha256": dataset_hash,
            "title": spec.title,
            "openapi_version": spec.openapi_version,
            "operations": len(spec.operations),
        },
        "config": config.to_dict(),
        "conditions": conditions,
        "seeds": seeds,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_model": _cpu_model(),
            "cpu_count": os.cpu_count(),
            "memory_gb": _memory_gb(),
            "packages": _package_versions(),
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "base_url": (
                "http://localhost:11434"
                if (settings.llm_provider or "").lower() == "ollama"
                and settings.llm_base_url.rstrip("/") == "https://api.openai.com/v1"
                else settings.llm_base_url
            ),
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_num_predict,
            "num_ctx": settings.llm_num_ctx,
            "ollama": _ollama_metadata(settings),
        },
        "prompt_schema": {
            "prompts_sha256": prompt_hash,
            "schemas_sha256": schema_hash,
        },
    }


def write_sha256sums(run_dir: Path) -> Path:
    """Write checksums for every immutable artifact in a run directory."""
    target = run_dir / "SHA256SUMS"
    lines = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.resolve() == target.resolve():
            continue
        relative = path.relative_to(run_dir).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target
