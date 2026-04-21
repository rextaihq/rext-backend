"""Compatibility patches for known LangGraph/LangGraph API edge cases."""

from __future__ import annotations

import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)


def apply_langgraph_patches() -> None:
    """
    Apply runtime-safe patches for LangGraph interoperability issues.

    Current patch:
    - Guard `_control_branch` against `Command(goto=None)` inputs. Some
      langgraph_api command payloads intentionally omit `goto`, but older
      langgraph versions attempt to iterate it and crash at `__start__`.
    """

    try:
        from langgraph.graph import state as lg_state
    except Exception:
        logger.exception("Unable to import langgraph state module for compatibility patch.")
        return

    if getattr(lg_state, "_rext_control_branch_patch_applied", False):
        return

    def _safe_control_branch(value: Any) -> Sequence[tuple[str, Any]]:
        if isinstance(value, lg_state.Send):
            return ((lg_state.TASKS, value),)

        commands: list[Any] = []
        if isinstance(value, lg_state.Command):
            commands.append(value)
        elif isinstance(value, (list, tuple)):
            commands.extend(cmd for cmd in value if isinstance(cmd, lg_state.Command))

        rtn: list[tuple[str, Any]] = []
        for command in commands:
            if command.graph == lg_state.Command.PARENT:
                raise lg_state.ParentCommand(command)

            goto = command.goto
            if goto is None:
                continue

            goto_targets = [goto] if isinstance(goto, (lg_state.Send, str)) else goto
            if goto_targets is None:
                continue

            for go in goto_targets:
                if isinstance(go, lg_state.Send):
                    rtn.append((lg_state.TASKS, go))
                elif isinstance(go, str) and go != lg_state.END:
                    rtn.append((lg_state._CHANNEL_BRANCH_TO.format(go), None))
        return rtn

    lg_state._control_branch = _safe_control_branch
    lg_state._rext_control_branch_patch_applied = True
    logger.info("Applied LangGraph compatibility patch for Command(goto=None).")

