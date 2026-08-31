"""Human-readable rendering of a publish package for the terminal."""

from __future__ import annotations

from .models import PublishPackage

_RULE = "─" * 60


def format_package(pkg: PublishPackage) -> str:
    """Render title/category/tags/paths + the full multi-line description.

    The description is printed raw (real newlines, no indent) so it can be
    copied straight into the upload form.
    """
    meta = pkg.metadata
    if meta is None:
        return f"✗ publish failed\n    {pkg.error}"

    lines = [f"✓ {meta.title}"]
    if meta.category:
        lines.append(f"    category: {meta.category}")
    if meta.tags:
        lines.append(f"    tags:     {', '.join(meta.tags)}")
    if pkg.metadata_path:
        lines.append(f"    meta:     {pkg.metadata_path}")
    if pkg.cover_path:
        lines.append(f"    cover:    {pkg.cover_path}")

    if meta.description.strip():
        lines += [_RULE, "description:", "", meta.description, _RULE]
    return "\n".join(lines)
