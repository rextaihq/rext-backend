"""A model that starts writing whitespace and doesn't stop (revnix/rext-control#697).

Asked for JSON, gpt-4o-mini now and then writes spaces and line breaks without end. On staging
(2026-10-07) one outline call wrote 26,402 whitespace characters in a row, until the 8,192-token
limit a minute and a half later, when its answer couldn't be read and the review step opened on
an empty outline; others came back after a minute with a valid outline. Four of eight how-to
outlines did one or the other.

Nothing a model is asked for here holds a long run of whitespace, so a watch on the stream stops
the call when one starts: a runaway costs a second instead of a minute. What the model had
written is usually the whole answer but for its closing brace (every runaway caught while this
was written began after the outline's last text field, where only fields with defaults were
left), so the answer is read from that when it fits the schema, and asked for once more when it
doesn't. An answer cut off at the token limit is asked for again the same way.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers.context import register_configure_hook
from openai import LengthFinishReasonError
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("rext.stage_timing")

# Whitespace characters in a row. Indented JSON has runs of a few dozen at most.
RUNAWAY_WHITESPACE = 400
# The same token again and again (an escaped line break inside a string, say): no answer has it.
RUNAWAY_REPEATS = 200


class WhitespaceRunaway(RuntimeError):
    """The model's output turned into a run of whitespace, or of one repeated token; the call
    was stopped. `text` is what it had written before that."""

    def __init__(self, message: str, text: str = ""):
        super().__init__(message)
        self.text = text


class WhitespaceWatch(BaseCallbackHandler):
    """Stops a streamed model call when its output turns into a long run of whitespace.

    One watch per call (see `ainvoke_watched`). It raises from `on_llm_new_token`, which ends
    the stream and with it the request; `raise_error` is what lets the exception out, and
    `run_inline` keeps the count on the loop, token by token, in order. It needs the model to
    stream (`load_model` does): a call answered in one piece has no tokens to watch.
    """

    raise_error = True
    run_inline = True

    def __init__(self, limit: int = RUNAWAY_WHITESPACE, repeats: int = RUNAWAY_REPEATS):
        self._limit = limit
        self._repeats = repeats
        self._whitespace: dict[UUID, int] = {}
        self._same: dict[UUID, tuple[str, int]] = {}
        self._written: dict[UUID, list[str]] = {}

    def on_llm_new_token(self, token: str, *, run_id: UUID, **kwargs: Any) -> None:
        if not isinstance(token, str) or not token:
            return
        written = self._written.setdefault(run_id, [])
        written.append(token)
        if token.isspace():
            run = self._whitespace.get(run_id, 0) + len(token)
        else:
            run = len(token) - len(token.rstrip())
        self._whitespace[run_id] = run
        last, times = self._same.get(run_id, ("", 0))
        times = times + 1 if token == last else 1
        self._same[run_id] = (token, times)
        if run >= self._limit:
            text = "".join(written).rstrip()
            self._forget(run_id)
            raise WhitespaceRunaway(f"the model wrote {run} whitespace characters in a row", text)
        if times >= self._repeats:
            text = "".join(written[:-times])
            self._forget(run_id)
            raise WhitespaceRunaway(f"the model wrote one token {times} times in a row", text)

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._forget(run_id)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._forget(run_id)

    def _forget(self, run_id: UUID) -> None:
        for kept in (self._whitespace, self._same, self._written):
            kept.pop(run_id, None)


# The watch of the call in progress. LangChain adds a handler found in a registered variable to
# every run configured while it is set (as its own usage and tracing collectors are), so the
# model's stream reaches the watch without a call site passing it down.
_watch: ContextVar[WhitespaceWatch | None] = ContextVar("whitespace_watch", default=None)
register_configure_hook(_watch, inheritable=True)


def _runaway(error: BaseException) -> WhitespaceRunaway | LengthFinishReasonError | None:
    """The runaway or cut-off an error is, or wraps (a few levels deep)."""
    seen = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(seen) < 8:
        seen.add(id(current))
        if isinstance(current, (WhitespaceRunaway, LengthFinishReasonError)):
            return current
        current = current.__cause__ or current.__context__
    return None


def ran_away(error: BaseException) -> str | None:
    """ "whitespace" or "cut_off" when the error is, or wraps, a runaway or an answer cut off at
    the token limit; None for any other error."""
    found = _runaway(error)
    if found is None:
        return None
    return "whitespace" if isinstance(found, WhitespaceRunaway) else "cut_off"


def answer_before_runaway(text: str, schema: type[BaseModel] | None) -> BaseModel | None:
    """The answer a stopped call had already written, when it is whole but for its closing brace.

    Only that: the text must end between two fields of the answer's own object (every list and
    inner object closed), and what it holds must fit the schema, so every required field is
    there and only fields with defaults are missing. Anything else is asked for again.
    """
    if schema is None or not text:
        return None
    body = text.rstrip().rstrip(",").rstrip()
    try:
        data = json.loads(body + "}")
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return schema.model_validate(data)
    except ValidationError:
        return None


async def ainvoke_watched(
    runnable: Any, messages: Any, *, stage: str, schema: type[BaseModel] | None = None
) -> Any:
    """`runnable.ainvoke(messages)` under the whitespace watch.

    A call that ran away is answered from what it had written when that is the whole answer
    (`schema` given: the structured output's own); otherwise, and when the answer was cut off at
    the token limit, it is asked once more. A second failure, and any other error, is the
    caller's.
    """
    for attempt in (1, 2):
        watching = _watch.set(WhitespaceWatch())
        try:
            return await runnable.ainvoke(messages)
        except Exception as error:
            found = _runaway(error)
            if found is None:
                raise
            answer = answer_before_runaway(getattr(found, "text", ""), schema)
            kept = "yes" if answer is not None else "no"
            logger.warning(
                f"stage_runaway stage={stage} reason={ran_away(error)} attempt={attempt} "
                f"answer_kept={kept}"
            )
            if answer is not None:
                return answer
            if attempt == 2:
                raise
        finally:
            _watch.reset(watching)
    raise AssertionError("unreachable")
