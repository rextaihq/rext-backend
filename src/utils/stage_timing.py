"""One log line per generation stage, with how long it took (rext-control#697).

`stage_timing stage=<name> ms=<n> outcome=<ok|error> [key=value ...]`, one line per stage
of the analysis and the outline, so each stage's p50 and p95 can be read from the server's
logs before and after a change, on staging and live. The line names no keyword and no user:
ids and outcomes only.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("rext.stage_timing")


@contextmanager
def timed_stage(stage: str, **fields: object) -> Iterator[dict]:
    """Time the block; the dict it yields takes fields learned inside it (cache="hit")."""
    extra: dict = dict(fields)
    started = time.perf_counter()
    outcome = "ok"
    try:
        yield extra
    except BaseException:
        outcome = "error"
        raise
    finally:
        ms = round((time.perf_counter() - started) * 1000)
        tail = "".join(f" {key}={value}" for key, value in extra.items())
        logger.info(f"stage_timing stage={stage} ms={ms} outcome={outcome}{tail}")
