"""Immutable records for the metrics datastore."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """A snapshot of an original (source) video's metrics."""

    source_id: str
    url: str | None = None
    title: str | None = None
    channel: str | None = None
    uploader: str | None = None
    upload_date: str | None = None
    duration_s: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    captured_at: str | None = None  # set by the store when omitted


@dataclass(frozen=True, slots=True)
class UploadRecord:
    """A snapshot of one of our re-uploaded videos' metrics."""

    source_id: str
    platform: str
    url: str | None = None
    title: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    captured_at: str | None = None


@dataclass(frozen=True, slots=True)
class Comparison:
    """Latest source vs. latest upload for one source video."""

    source_id: str
    source: SourceRecord | None
    upload: UploadRecord | None

    def view_ratio(self) -> float | None:
        """Upload views as a fraction of source views, if both are known."""
        if self.source and self.upload and self.source.view_count:
            if self.upload.view_count is not None:
                return self.upload.view_count / self.source.view_count
        return None
