"""Write a per-run diagnostic manifest next to the output.

The terminal prints a per-phase "engines (local vs cloud)" summary, but that's
gone once the run ends. This records the same info — plus each stage's status,
the dub voice, and any error — as `<video>.run.json` beside the artifacts, so
when a dub comes out silent or a video looks off you can see exactly which
engine produced each phase after the fact.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("transdub.flow")


def build_manifest(result) -> dict:
    """Serialize a FlowResult into a diagnostic dict (JSON-ready)."""
    manifest: dict = {
        "url": result.url,
        "status": result.status,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engines": dict(result.engines or {}),
    }
    if result.error:
        manifest["error"] = result.error

    stages: dict = {}
    if result.download is not None:
        stages["download"] = {"ok": result.download.ok}
    if result.translation is not None:
        stages["translate"] = {
            "ok": result.translation.ok,
            "subtitle_source": getattr(result.translation, "subtitle_source", None),
        }
    if result.compose is not None:
        stages["compose"] = {"ok": result.compose.ok, "output": _s(result.compose.out_path)}
    if result.dub is not None:
        stages["dub"] = {
            "ok": result.dub.ok,
            "voice": result.dub.voice or None,
            "output": _s(result.dub.out_path),
            "error": result.dub.error,
        }
    if result.publish is not None:
        stages["publish"] = {
            "ok": result.publish.ok,
            "metadata": _s(getattr(result.publish, "metadata_path", None)),
        }
    manifest["stages"] = stages
    return manifest


def write_run_manifest(result, output_dir: str | Path = "output") -> Path | None:
    """Write `<video>.run.json` beside the output; return its path (or None).

    Located next to the final video when there is one, otherwise mirrored into
    the output tree from the downloaded video. Best-effort: never raises.
    """
    path = _manifest_path(result, output_dir)
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(build_manifest(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path
    except Exception as err:  # diagnostics must never sink a run
        log.debug("could not write run manifest: %s", err)
        return None


def _manifest_path(result, output_dir: str | Path) -> Path | None:
    """`<final>.final.run.json` when composed, else `<video>.run.json` mirrored."""
    if result.compose is not None and result.compose.out_path:
        return Path(result.compose.out_path).with_suffix(".run.json")
    if result.download is not None and result.download.video_path:
        from publish.package import mirrored_dir

        video = Path(result.download.video_path)
        return mirrored_dir(video, output_dir) / f"{video.stem}.run.json"
    return None


def _s(value) -> str | None:
    return str(value) if value is not None else None
