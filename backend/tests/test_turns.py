"""Reads take turns (app/web/turns.py): first come, first served, while reads are quick. A request that changes
something waits for nobody, and a read that is stuck stops holding the others up after its turn."""
from __future__ import annotations

import asyncio

import pytest

from app.web.turns import OneReadAtATime


def _scope(path: str = "/api/plans/1", method: str = "GET", **more) -> dict:
    return {"type": "http", "method": method, "path": path, "headers": [], **more}


class _App:
    """A stand-in for the app: it notes the order requests reach it and how many views are being worked out at once."""

    def __init__(self) -> None:
        self.working = 0
        self.most = 0
        self.order: list[str] = []
        self.done: list[str] = []
        self.hold_view: dict[str, asyncio.Event] = {}        # a view that is not worked out until its event is set
        self.hold_body: dict[str, asyncio.Event] = {}        # an answer whose body waits (a slow download)

    async def __call__(self, scope, receive, send) -> None:
        name = scope["path"]
        self.order.append(name)
        self.working += 1
        self.most = max(self.most, self.working)
        try:
            await asyncio.sleep(0.005)
            if name in self.hold_view:
                await self.hold_view[name].wait()
            if scope.get("fails"):
                raise RuntimeError("the view could not be worked out")
        finally:
            self.working -= 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        if name in self.hold_body:
            await self.hold_body[name].wait()
        await send({"type": "http.response.body", "body": b"{}"})
        self.done.append(name)


async def _ask(gate, scope) -> list[dict]:
    sent: list[dict] = []

    async def send(message) -> None:
        sent.append(message)

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    await gate(scope, receive, send)
    return sent


def test_reads_are_worked_out_one_at_a_time_in_the_order_they_came():
    async def main():
        app = _App()
        gate = OneReadAtATime(app)
        names = [f"/api/plans/{n}" for n in range(1, 9)]
        answers = await asyncio.gather(*[_ask(gate, _scope(name)) for name in names])
        return app, names, answers

    app, names, answers = asyncio.run(main())
    assert app.most == 1                                     # never two views at once
    assert app.order == names and app.done == names          # first come, first served
    assert all([m["type"] for m in sent] == ["http.response.start", "http.response.body"] for sent in answers)   # every answer whole, none changed


def test_without_the_turns_the_same_reads_would_be_worked_out_side_by_side():
    # (the stand-in really does overlap when nothing makes the reads wait: the test above measures the middleware, not the stand-in)
    async def main():
        app = _App()
        await asyncio.gather(*[_ask(app, _scope(f"/api/plans/{n}")) for n in range(1, 9)])
        return app

    assert asyncio.run(main()).most > 1


def test_a_request_that_changes_something_takes_no_turn_and_waits_for_none():
    async def main():
        app = _App()
        gate = OneReadAtATime(app)
        app.hold_view["/api/plans/1/lab"] = asyncio.Event()
        slow = asyncio.create_task(_ask(gate, _scope("/api/plans/1/lab")))
        await asyncio.sleep(0.02)                            # the read has its turn and is still being worked out
        # a change, a page file and a read that is not under /api all go straight through
        for scope in (_scope("/api/plans/1/run-all", "POST"), _scope("/assets/index.js"), _scope("/")):
            await asyncio.wait_for(_ask(gate, scope), timeout=10)
        waiting = asyncio.create_task(_ask(gate, _scope("/api/plans/1/checks")))
        await asyncio.sleep(0.02)
        assert not slow.done() and not waiting.done()        # the second read waits for the first
        assert "/api/plans/1/checks" not in app.order
        app.hold_view["/api/plans/1/lab"].set()
        await asyncio.wait_for(asyncio.gather(slow, waiting), timeout=10)
        return app

    app = asyncio.run(main())
    assert app.order == ["/api/plans/1/lab", "/api/plans/1/run-all", "/assets/index.js", "/", "/api/plans/1/checks"]


def test_the_turn_ends_when_the_answer_starts_so_a_slow_download_holds_nobody_back():
    async def main():
        app = _App()
        gate = OneReadAtATime(app)
        app.hold_body["/api/evidence/1/json"] = asyncio.Event()
        download = asyncio.create_task(_ask(gate, _scope("/api/evidence/1/json")))
        await asyncio.sleep(0.02)                            # its answer has started; the body is still going out
        after = await asyncio.wait_for(_ask(gate, _scope("/api/plans/1")), timeout=10)
        assert not download.done() and [m["type"] for m in after] == ["http.response.start", "http.response.body"]
        app.hold_body["/api/evidence/1/json"].set()
        await asyncio.wait_for(download, timeout=10)

    asyncio.run(main())


def test_a_read_that_fails_gives_its_turn_back():
    async def main():
        app = _App()
        gate = OneReadAtATime(app)
        with pytest.raises(RuntimeError):
            await _ask(gate, _scope("/api/plans/1", fails=True))
        # and one that is dropped while it waits for its turn does not keep a place in the queue
        app.hold_view["/api/plans/2"] = asyncio.Event()
        first = asyncio.create_task(_ask(gate, _scope("/api/plans/2")))
        await asyncio.sleep(0.02)
        dropped = asyncio.create_task(_ask(gate, _scope("/api/plans/3")))
        await asyncio.sleep(0.02)
        dropped.cancel()
        app.hold_view["/api/plans/2"].set()
        await asyncio.wait_for(first, timeout=10)
        return await asyncio.wait_for(_ask(gate, _scope("/api/plans/4")), timeout=10), app

    answer, app = asyncio.run(main())
    assert [m["type"] for m in answer] == ["http.response.start", "http.response.body"]
    assert "/api/plans/3" not in app.order


def test_a_read_that_is_stuck_holds_the_others_for_one_turn_only_and_then_they_go_side_by_side():
    # Some reads wait for work a person started that takes long (a change being written with Live Otto on, a setting
    # being applied). Such a read must not stop every other page from reading.
    async def main():
        app = _App()
        gate = OneReadAtATime(app, limit=0.3)      # (long beside the short waits below, so a busy machine does not blur the order)
        app.hold_view["/api/import/1/migration"] = asyncio.Event()
        stuck = asyncio.create_task(_ask(gate, _scope("/api/import/1/migration")))
        await asyncio.sleep(0.01)
        waiting = [asyncio.create_task(_ask(gate, _scope(f"/api/plans/{n}"))) for n in (1, 2, 3)]
        await asyncio.sleep(0.01)
        assert app.order == ["/api/import/1/migration"]              # within its turn the others wait
        await asyncio.wait_for(asyncio.gather(*waiting), timeout=10)    # after it they are answered, although it never answered
        assert not stuck.done()
        # while it is stuck nobody waits for a turn: reads that come now are worked out side by side, as before there were turns
        app.most = 0
        app.hold_view["/api/plans/7"] = asyncio.Event()
        slow = asyncio.create_task(_ask(gate, _scope("/api/plans/7")))
        await asyncio.sleep(0.01)
        await asyncio.wait_for(_ask(gate, _scope("/api/plans/8")), timeout=10)      # not held up by the slow one before it
        app.hold_view["/api/plans/7"].set()
        await asyncio.wait_for(slow, timeout=10)
        side_by_side = app.most
        # once the stuck read has answered, the reads take turns again
        app.hold_view["/api/import/1/migration"].set()
        await asyncio.wait_for(stuck, timeout=10)
        app.most = 0
        await asyncio.gather(*[_ask(gate, _scope(f"/api/plans/{n}")) for n in range(10, 16)])
        return side_by_side, app.most, app

    side_by_side, in_turn, app = asyncio.run(main())
    assert side_by_side > 1 and in_turn == 1
    assert "/api/import/1/migration" in app.done                     # the stuck read's own answer went out whole in the end


def test_a_quick_read_never_runs_past_its_turn():
    # (the limit's timer is put away with the answer: a read that answered in time is not counted as stuck later)
    async def main():
        app = _App()
        gate = OneReadAtATime(app, limit=0.05)
        await _ask(gate, _scope("/api/plans/1"))
        await asyncio.sleep(0.1)                                     # well past the limit
        app.most = 0
        await asyncio.gather(*[_ask(gate, _scope(f"/api/plans/{n}")) for n in range(2, 8)])
        return app.most

    assert asyncio.run(main()) == 1


def test_each_event_loop_has_its_own_turns():
    # The app has one event loop; every test client brings its own. Reads that queue up in one loop must not trip over
    # the queue of another (a lock made in one loop cannot be waited for in another).
    app = _App()
    gate = OneReadAtATime(app)

    async def main():
        await asyncio.gather(*[_ask(gate, _scope(f"/api/plans/{n}")) for n in range(1, 5)])

    for _ in range(3):
        asyncio.run(main())
    assert app.most == 1 and len(app.done) == 12


def test_the_app_itself_answers_reads_in_turn(client):
    # The app really has the turns, around everything else it does with a request.
    assert client.app.user_middleware[0].cls is OneReadAtATime
    # Through the real app: a read and a change both come back as before (nothing in an answer is changed).
    assert client.get("/api/session").status_code == 200
    assert client.get("/api/no-such-thing").status_code == 404
    assert client.post("/api/no-such-thing").status_code in (401, 404, 405)
