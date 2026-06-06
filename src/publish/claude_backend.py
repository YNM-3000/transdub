"""Claude implementation of MetadataBackend.

Generates a Chinese title, description, and tags for a repurposed life/
knowledge video. Uses a labeled-section text protocol (TITLE / TAGS /
DESCRIPTION) rather than JSON — robust to punctuation in the generated copy,
consistent with the translator's wire-format choice.
"""

from __future__ import annotations

import os
import re
import time

from .models import PublishMetadata

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
BACKOFF_BASE_S = 2.0
MAX_CONTENT_CHARS = 4000

SYSTEM_PROMPT = """\
You run a Chinese video channel (bilibili / 抖音 / 西瓜视频) that republishes
overseas life- and knowledge-style videos (everyday phenomena, product design,
things people overlook). Given a source title and the video's Chinese content,
write platform-native metadata.

Guidelines:
- Title: one catchy line in Chinese, <= 30 characters, accurate, not
  exaggerated clickbait.
- Category: ONE best-fit category for grouping into collections. Prefer one of:
  生活技巧、产品设计、科技数码、汽车交通、健康医学、美食料理、居家家装、
  自然科学、历史人文、心理行为、商业经济、其他。If none fits, coin a short
  Chinese category of your own.
- Description: 2-4 sentences in Chinese summarizing the content with a hook;
  may note it is translated/搬运 overseas content.
- Tags: 5-10 relevant Chinese keywords.

Output format, EXACTLY these labeled sections, nothing else:
TITLE: <一行中文标题>
CATEGORY: <一个最合适的中文分类>
TAGS: 标签1, 标签2, 标签3
DESCRIPTION:
<中文简介，可多行>
"""

_TITLE = re.compile(r"^\s*TITLE\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
_CATEGORY = re.compile(r"^\s*CATEGORY\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
_TAGS = re.compile(r"^\s*TAGS\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
_DESC = re.compile(r"DESCRIPTION\s*[:：]\s*\n?(.*)$", re.DOTALL)
_TAG_SPLIT = re.compile(r"[,，、]")


class ClaudeMetadataBackend:
    """Generate publish metadata via the Anthropic Messages API."""

    def __init__(
        self,
        client: object | None = None,
        model: str | None = None,
        max_retries: int = MAX_RETRIES,
        sleep=time.sleep,
    ) -> None:
        self._client = client
        self._model = model or os.environ.get("RECREATOR_MODEL", DEFAULT_MODEL)
        self._max_retries = max_retries
        self._sleep = sleep

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, source_title: str, content: str) -> PublishMetadata:
        user = (
            f"Source title: {source_title}\n\n"
            f"Chinese content (subtitle text):\n{content[:MAX_CONTENT_CHARS]}\n\n"
            "Write the metadata in the required labeled format."
        )

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return _parse_metadata(self._request(user))
            except Exception as err:
                if _is_non_retryable(err):
                    raise
                last_err = err
            if attempt < self._max_retries - 1:
                self._sleep(BACKOFF_BASE_S * (2**attempt))

        raise RuntimeError(f"metadata generation failed: {last_err}") from last_err

    def _request(self, user: str) -> str:
        message = self.client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


def _is_non_retryable(err: Exception) -> bool:
    status = getattr(err, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500 and status != 429


def _parse_metadata(text: str) -> PublishMetadata:
    title_m = _TITLE.search(text)
    if not title_m:
        raise ValueError(f"no TITLE in metadata response: {text[:160]!r}")
    title = title_m.group(1).strip()

    category_m = _CATEGORY.search(text)
    category = category_m.group(1).strip() if category_m else ""

    tags: tuple[str, ...] = ()
    tags_m = _TAGS.search(text)
    if tags_m:
        tags = tuple(t.strip() for t in _TAG_SPLIT.split(tags_m.group(1)) if t.strip())

    desc_m = _DESC.search(text)
    description = desc_m.group(1).strip() if desc_m else ""

    return PublishMetadata(title=title, description=description, tags=tags, category=category)
