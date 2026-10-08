"""A run never reaches the database from its own loop (revnix/rext-control#858).

The runtime takes runs from its queue before this app's startup has finished. Until startup
registered the main loop, which it did last, the bridge ran a worker thread's database work on
the worker's own loop, against the pool the main loop owns: a connection left inside a
transaction, and later requests on it answered as saved that never were. The bridge now keeps
a worker thread waiting for the main loop, and fails its step loudly if none appears.
"""

import asyncio
import inspect
import threading

import pytest

from src.utils import credit_manager, loop_bridge, loop_registry
from src.utils.loop_bridge import MainLoopNotReady, run_on_main_loop


@pytest.fixture(autouse=True)
def _no_main_loop(monkeypatch):
    """Every test starts as a process does: no main loop registered."""
    monkeypatch.setattr(loop_registry, "_main_loop", None)


class _ServerLoop:
    """A loop running in a thread of its own, standing in for the server's main loop."""

    def __enter__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        return self.loop

    def __exit__(self, *error):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()


def _on_a_worker_loop(make_coroutine, thread_name="bg-loop-0_0"):
    """Run ``make_coroutine()`` to its end on a loop of its own in a worker thread, as the
    runtime runs a job; returns (result, error, the worker's loop)."""
    box = {}

    def work():
        loop = asyncio.new_event_loop()
        box["loop"] = loop
        try:
            box["result"] = loop.run_until_complete(make_coroutine())
        except BaseException as error:  # noqa: BLE001 - handed back to the test
            box["error"] = error
        finally:
            loop.close()

    # Named as the runtime names the threads it runs jobs on.
    thread = threading.Thread(target=work, name=thread_name)
    thread.start()
    thread.join(timeout=20)
    assert not thread.is_alive(), "the worker never finished"
    return box.get("result"), box.get("error"), box["loop"]


async def _which_loop():
    return asyncio.get_running_loop()


def test_a_run_started_before_the_main_loop_is_registered_waits_for_it_and_runs_there():
    """The reported case: the worker reaches its first database call while startup is still
    under way. Its work runs on the main loop once that is known, never on its own."""
    with _ServerLoop() as server_loop:
        # Startup registers the loop a moment after the run has begun.
        threading.Timer(0.3, loop_registry.register, args=(server_loop,)).start()

        ran_on, error, worker_loop = _on_a_worker_loop(lambda: run_on_main_loop(_which_loop()))

    assert error is None
    assert ran_on is server_loop
    assert ran_on is not worker_loop


def test_a_worker_thread_with_a_registered_main_loop_runs_its_work_there():
    with _ServerLoop() as server_loop:
        loop_registry.register(server_loop)

        ran_on, error, worker_loop = _on_a_worker_loop(lambda: run_on_main_loop(_which_loop()))

    assert error is None and ran_on is server_loop and ran_on is not worker_loop


def test_a_worker_thread_whose_main_loop_never_appears_fails_loudly_and_runs_nothing(monkeypatch):
    monkeypatch.setattr(loop_bridge, "MAIN_LOOP_WAIT_SECONDS", 0.2)
    started = []

    async def database_work():
        started.append(asyncio.get_running_loop())

    work = database_work()
    _, error, _ = _on_a_worker_loop(lambda: run_on_main_loop(work))

    assert isinstance(error, MainLoopNotReady)
    assert "was not registered within 0.2 seconds" in str(error)
    # Never started, on any loop, and closed: not left as a coroutine nobody awaited.
    assert started == []
    assert inspect.getcoroutinestate(work) == inspect.CORO_CLOSED


def test_a_thread_that_is_not_one_of_the_runtimes_runs_its_work_where_it_is():
    """A test client runs the app on a loop in a thread of its own, and a script may too:
    with no main loop registered, that loop is the only one there is. Only the runtime's
    job threads are known to be beside a server whose loop owns the pool."""
    ran_on, error, own_loop = _on_a_worker_loop(
        lambda: run_on_main_loop(_which_loop()), thread_name="asyncio-portal-1"
    )

    assert error is None and ran_on is own_loop


def test_the_runtime_still_names_its_job_threads_as_the_bridge_expects():
    """The bridge knows a job's thread by the runtime's name for it. Read from the runtime's
    own source, so an upgrade that renames them fails here."""
    import langgraph_runtime_inmem.queue as runtime_queue

    assert f'thread_name_prefix=f"{loop_bridge.JOB_THREAD_PREFIX}' in inspect.getsource(
        runtime_queue
    )


async def test_on_the_main_thread_with_no_main_loop_the_work_runs_where_it_is():
    """A script, a test, or the server's own loop before startup registered it: this loop is
    the only one there is, and the one the pool belongs to."""
    assert await run_on_main_loop(_which_loop()) is asyncio.get_running_loop()


async def test_on_the_main_loop_itself_the_work_runs_directly():
    loop_registry.register(asyncio.get_running_loop())

    assert await run_on_main_loop(_which_loop()) is asyncio.get_running_loop()


def test_the_credits_go_through_the_same_bridge(monkeypatch):
    """credit_manager had a copy of the bridge with the same fallback to the caller's loop."""
    monkeypatch.setattr(loop_bridge, "MAIN_LOOP_WAIT_SECONDS", 0.2)
    started = []

    async def read_the_balance():
        started.append(1)

    _, error, _ = _on_a_worker_loop(lambda: credit_manager._run_on_main_loop(read_the_balance()))

    assert isinstance(error, MainLoopNotReady) and started == []

    with _ServerLoop() as server_loop:
        loop_registry.register(server_loop)
        ran_on, error, worker_loop = _on_a_worker_loop(
            lambda: credit_manager._run_on_main_loop(_which_loop())
        )
    assert error is None and ran_on is server_loop and ran_on is not worker_loop


def test_an_analytics_event_is_never_sent_from_a_runs_own_loop():
    """`send_soon` started the send on the running loop when no main loop was registered; its
    read of the person then used the pool from the run's loop. It is dropped instead."""
    from src.services.server_events import send_soon

    started = []

    async def sending():
        started.append(asyncio.get_running_loop())

    async def from_a_run():
        send_soon(sending())
        await asyncio.sleep(0.05)

    _, error, _ = _on_a_worker_loop(from_a_run)

    assert error is None and started == []

    with _ServerLoop() as server_loop:
        loop_registry.register(server_loop)
        _, error, worker_loop = _on_a_worker_loop(from_a_run)
    assert error is None and started == [server_loop]


async def test_startup_registers_the_main_loop_before_anything_else(monkeypatch):
    """The runtime's run queue is already going when this app's startup begins: the first
    thing startup does is say which loop the pool belongs to."""
    from src.api import server

    seen = {}

    def first_step_after(_settings):
        seen["loop"] = loop_registry.get()
        raise RuntimeError("stop the startup here")

    class _Stop(Exception):
        pass

    async def no_migrations():
        raise _Stop

    monkeypatch.setattr(server, "init_sentry", first_step_after)
    monkeypatch.setattr(server.settings, "MIGRATE_ON_START", True)
    monkeypatch.setattr("src.api.database.migrate_on_start.apply_pending_migrations", no_migrations)
    monkeypatch.setattr("src.api.lib.error_log_capture.install_error_log_capture", lambda: False)

    with pytest.raises(_Stop):
        async with server.lifespan(server.app):
            pass

    assert seen["loop"] is asyncio.get_running_loop()
    # Nothing that can wait stands before it in the function.
    source = inspect.getsource(server.lifespan)
    assert source.index("loop_registry.register(") < source.index("await ")


# -- The error log, written from a run's node -----------------------------------------------


def test_an_error_logged_from_a_runs_node_is_written_on_the_main_loop(monkeypatch):
    """A run refused for credits, a failed search lookup and a failed model call each log a
    row from a node, on the run's own loop. The row was written there, through the app's
    pool: the same fault as above, on ordinary runs and with no restart."""
    from src.api.database import async_database
    from src.services.monitoring_service import MonitoringService

    written_on = []

    class _Session:
        async def __aenter__(self):
            written_on.append(asyncio.get_running_loop())
            return self

        async def __aexit__(self, *error):
            return False

        def add(self, entry):
            self.entry = entry

        async def commit(self):
            written_on.append(asyncio.get_running_loop())

    monkeypatch.setattr(async_database, "AsyncSessionLocal", _Session)

    async def from_a_node():
        await MonitoringService.persist_error_log(
            api_severity="medium",
            message="Content generation blocked: insufficient credits",
            source="flow rext.insufficient_credits",
            path="/flow/rext/insufficient_credits",
        )

    with _ServerLoop() as server_loop:
        loop_registry.register(server_loop)
        _, error, worker_loop = _on_a_worker_loop(from_a_node)

    assert error is None
    assert written_on == [server_loop, server_loop]
    assert worker_loop not in written_on


def test_an_error_logged_before_the_main_loop_is_known_is_dropped_not_written_from_the_run(
    monkeypatch,
):
    from src.api.database import async_database
    from src.services.monitoring_service import MonitoringService

    monkeypatch.setattr(loop_bridge, "MAIN_LOOP_WAIT_SECONDS", 0.2)
    opened = []
    monkeypatch.setattr(async_database, "AsyncSessionLocal", lambda: opened.append(1))

    async def from_a_node():
        # Logging never fails the step that logs: the row is lost, the run goes on.
        await MonitoringService.persist_error_log(
            api_severity="medium", message="x", source="flow x", path="/flow/x"
        )
        return "the node went on"

    result, error, _ = _on_a_worker_loop(from_a_node)

    assert error is None and result == "the node went on"
    assert opened == []


def test_a_failed_model_call_is_reported_to_the_servers_loop_not_the_first_runs():
    """The sync reporter kept the loop it was first built on, which is a run's own when a
    node builds the model: closed when that run ended, and every later report was lost."""
    from src.flow.model import llm_manager

    reported_on = []

    async def report(service, error):
        reported_on.append(asyncio.get_running_loop())

    first_runs_loop = asyncio.new_event_loop()
    first_runs_loop.close()
    with pytest.MonkeyPatch.context() as patch, _ServerLoop() as server_loop:
        patch.setattr(llm_manager, "_MAIN_LOOP", first_runs_loop)
        patch.setattr(llm_manager, "_report_ai_failure", report)
        loop_registry.register(server_loop)

        llm_manager._SyncAIProviderFailureReporter("OpenAI").on_llm_error(RuntimeError("down"))
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.05), server_loop).result(timeout=5)

    assert reported_on == [server_loop]
