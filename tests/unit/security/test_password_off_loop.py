"""Hashing and checking a password never block the event loop (G39, revnix/rext-control#390).

bcrypt spends a few hundred milliseconds of CPU on each call; on the loop, a burst of
sign-ins would stall every other request.
"""

import ast
import threading
from pathlib import Path

import pytest

from src.api.security import token_utils
from src.api.security.token_utils import hash_password_async, verify_password_async

SRC = Path(__file__).resolve().parents[3] / "src"
BLOCKING = {"hash_password", "verify_password", "hashpw", "checkpw"}


@pytest.mark.asyncio
async def test_a_password_is_hashed_and_checked_in_a_worker_thread(monkeypatch):
    threads = []
    real_hashpw, real_checkpw = token_utils.bcrypt.hashpw, token_utils.bcrypt.checkpw

    def hashpw(*args):
        threads.append(threading.current_thread())
        return real_hashpw(*args)

    def checkpw(*args):
        threads.append(threading.current_thread())
        return real_checkpw(*args)

    monkeypatch.setattr(token_utils.bcrypt, "hashpw", hashpw)
    monkeypatch.setattr(token_utils.bcrypt, "checkpw", checkpw)

    hashed = await hash_password_async("A-made-up-password-1")
    assert await verify_password_async("A-made-up-password-1", hashed) is True
    assert await verify_password_async("Another-password-2", hashed) is False

    assert len(threads) == 3
    assert all(thread is not threading.main_thread() for thread in threads)


@pytest.mark.asyncio
async def test_an_account_without_a_password_never_matches():
    assert await verify_password_async("anything", None) is False
    assert await verify_password_async("anything", "oauth_no_password") is False


class _BlockingCalls(ast.NodeVisitor):
    """Calls to bcrypt, or to the sync helpers, made directly in an async function's body."""

    def __init__(self):
        self.found, self._in_async = [], False

    def _visit_body(self, node, in_async):
        outer, self._in_async = self._in_async, in_async
        self.generic_visit(node)
        self._in_async = outer

    def visit_AsyncFunctionDef(self, node):
        self._visit_body(node, True)

    def visit_FunctionDef(self, node):
        self._visit_body(node, False)  # a sync function may run in a thread

    def visit_Lambda(self, node):
        self._visit_body(node, False)  # e.g. asyncio.to_thread(lambda: ...)

    def visit_Call(self, node):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if self._in_async and name in BLOCKING:
            self.found.append(node.lineno)
        self.generic_visit(node)


def test_no_async_function_calls_bcrypt_on_the_loop():
    offenders = []
    for path in SRC.rglob("*.py"):
        visitor = _BlockingCalls()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        offenders += [f"{path.relative_to(SRC.parent)}:{line}" for line in visitor.found]

    assert offenders == []
