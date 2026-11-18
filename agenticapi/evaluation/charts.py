"""Small dependency-free SVG chart helpers."""

from __future__ import annotations

from pathlib import Path


def bar_chart(
    values: dict[str, float],
    *,
    title: str,
    y_label: str = "",
    width: int = 720,
    bar_height: int = 26,
    max_value: float | None = None,
) -> str:
    items = list(values.items())
    height = 80 + max(1, len(items)) * (bar_height + 12)
    if not items:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="120"></svg>'
    maximum = max_value if max_value is not None else max(values.values() or [1.0])
    maximum = maximum or 1.0
    left = 190
    right = 40
    usable = width - left - right
    rows = []
    for index, (label, value) in enumerate(items):
        y = 56 + index * (bar_height + 12)
        bar_width = max(0.0, min(1.0, value / maximum)) * usable
        rows.append(
            f'<text x="12" y="{y + 17}" font-family="sans-serif" font-size="13">{_escape(label)}</text>'
        )
        rows.append(
            f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="{bar_height}" '
            f'fill="#2f6f9f" rx="3"/>'
        )
        rows.append(
            f'<text x="{left + bar_width + 6:.2f}" y="{y + 17}" '
            f'font-family="sans-serif" font-size="13">{value:.3f}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'role="img" aria-label="{_escape(title)}">'
        f'<text x="12" y="26" font-family="sans-serif" font-size="18" font-weight="bold">'
        f"{_escape(title)}</text>"
        + "".join(rows)
        + (
            f'<text x="12" y="{height - 8}" font-family="sans-serif" font-size="11">'
            f"{_escape(y_label)}</text>"
        )
        + "</svg>"
    )


def write_chart(path: Path, svg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
