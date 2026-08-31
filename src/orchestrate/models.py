"""Result model for the end-to-end flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from download.models import DownloadResult

# Terminal statuses for one URL through the flow.
TRANSLATED = "translated"
DOWNLOAD_FAILED = "download_failed"
NO_SUBTITLE = "no_subtitle"
TRANSCRIBE_FAILED = "transcribe_failed"
TRANSLATE_FAILED = "translate_failed"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Outcome of taking one URL from download through translation."""

    url: str
    status: str
    download: DownloadResult | None = None
    ass_path: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == TRANSLATED
