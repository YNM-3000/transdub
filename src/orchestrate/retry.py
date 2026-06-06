"""Retry policy for flow stages.

Stages return result objects with an `ok` flag rather than raising, so retry
is driven by a success predicate; raised exceptions are also treated as
retryable failures and re-raised only if every attempt raises.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff for the 0-based attempt index, capped."""
        return min(self.max_delay, self.base_delay * (2**attempt))


def retry(
    fn: Callable[[], object],
    policy: RetryPolicy,
    *,
    success: Callable[[object], bool] = lambda _r: True,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, object], None] | None = None,
):
    """Call `fn()` until `success(result)` or attempts are exhausted.

    Returns the last result. If `fn` raises on every attempt, the final
    exception is re-raised. `on_retry(next_attempt, failure)` is invoked before
    each delay, where `failure` is the exception or the failed result.
    """
    last_result = None
    last_exc: Exception | None = None
    for attempt in range(policy.attempts):
        try:
            last_result = fn()
            last_exc = None
            if success(last_result):
                return last_result
            failure: object = last_result
        except Exception as exc:  # treat as a retryable failure
            last_exc = exc
            last_result = None
            failure = exc

        if attempt < policy.attempts - 1:
            if on_retry is not None:
                on_retry(attempt + 1, failure)
            sleep(policy.delay_for(attempt))

    if last_exc is not None:
        raise last_exc
    return last_result
