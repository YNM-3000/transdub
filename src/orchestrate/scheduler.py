"""Minimal interval scheduler for running a task repeatedly.

For production you may prefer cron/launchd invoking the CLI; this foreground
loop is handy for a long-running worker and is fully testable via injected
`sleep` + bounded `max_runs`.
"""

from __future__ import annotations

import time
from typing import Callable


def run_periodically(
    task: Callable[[], object],
    interval_s: float,
    *,
    max_runs: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_error: Callable[[Exception], None] | None = None,
) -> int:
    """Run `task` every `interval_s` seconds. Returns the number of runs.

    `max_runs` bounds the loop (None = forever). If `on_error` is given,
    exceptions from `task` are passed to it and the loop continues; otherwise
    they propagate.
    """
    runs = 0
    while True:
        try:
            task()
        except Exception as exc:
            if on_error is None:
                raise
            on_error(exc)
        runs += 1
        if max_runs is not None and runs >= max_runs:
            return runs
        sleep(interval_s)
