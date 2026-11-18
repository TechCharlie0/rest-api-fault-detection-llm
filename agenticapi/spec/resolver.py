"""Local JSON Reference resolution with cycle protection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class RefResolutionError(ValueError):
    pass


def _pointer_parts(ref: str) -> list[str]:
    if not ref.startswith("#/"):
        raise RefResolutionError(f"only local refs are supported: {ref}")
    return [part.replace("~1", "/").replace("~0", "~") for part in ref[2:].split("/")]


def resolve_pointer(root: dict[str, Any], ref: str) -> Any:
    node: Any = root
    for part in _pointer_parts(ref):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError) as exc:
                raise RefResolutionError(f"unresolvable ref: {ref}") from exc
        else:
            raise RefResolutionError(f"unresolvable ref: {ref}")
    return node


def resolve(value: Any, root: dict[str, Any], stack: tuple[str, ...] = ()) -> Any:
    """Resolve local refs recursively.  Cycles are preserved as unresolved refs."""
    if isinstance(value, list):
        return [resolve(item, root, stack) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str):
            raise RefResolutionError(f"$ref must be a string: {ref!r}")
        if ref in stack:
            result = {"$ref": ref, "x-agenticapi-cycle": True}
            extra = {k: resolve(v, root, stack) for k, v in value.items() if k != "$ref"}
            result.update(extra)
            return result
        target = deepcopy(resolve_pointer(root, ref))
        resolved = resolve(target, root, stack + (ref,))
        if extra := {k: resolve(v, root, stack) for k, v in value.items() if k != "$ref"}:
            if isinstance(resolved, dict):
                resolved.update(extra)
            else:
                return {"value": resolved, **extra}
        return resolved
    return {k: resolve(v, root, stack) for k, v in value.items()}
