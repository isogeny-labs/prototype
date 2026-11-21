"""One read at a time, while reads are quick.

A page asks for several views at once: its own, the Related block of an open item, the Otto panel's. Each view is
worked out from many small database reads, and Python works several of them out side by side much more slowly than one
after another: the same twelve views took about 3 seconds in a row and about 7 seconds when six were worked out at once
(measured on 19 November 2026, on four cores). With the Otto panel beside every page that turned a quick walk through
the pages into a queue, and the Overview's own numbers arrived seconds late.

So the reads under /api take turns, in the order they arrive. A turn ends when the answer starts to go out, so a slow
download holds nobody back. A request that changes something (anything that is not a GET) takes no turn and waits for
none.

A read can be slow for a reason that has nothing to do with the others: some reads wait for work that a person
started and that takes long (a change being written with Live Otto on, a setting being applied on a test server).
Such a read must not stop every other page from reading, so a turn also ends after `LIMIT` seconds. From then until
that read has answered, nobody waits for a turn: the reads go side by side, as they did before there were turns. The
worst a stuck read costs the others is that one wait.

Nothing is decided here, and no answer is changed.
"""
from __future__ import annotations

import asyncio
import weakref

LIMIT = 5.0   # seconds one read may hold its turn; an ordinary view takes well under two


# Hosting: the health check (a load balancer's probe) and the GitHub login (which waits on GitHub) read no view.
UNQUEUED = frozenset({"/api/health", "/api/auth/github/start", "/api/auth/github/callback"})


class _Turns:
    """The turns of one event loop."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.stuck = 0          # reads that ran past their turn and have not answered yet


class OneReadAtATime:
    """Web middleware: GET requests under /api are answered one after another, first come, first served, for as long
    as each is answered within `limit` seconds."""

    def __init__(self, app, limit: float = LIMIT) -> None:
        self.app = app
        self.limit = limit
        # (one set of turns for each event loop: the app has one, and every test client brings its own)
        self._turns: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _Turns] = weakref.WeakKeyDictionary()

    def _for_this_loop(self) -> _Turns:
        loop = asyncio.get_running_loop()
        turns = self._turns.get(loop)
        if turns is None:
            turns = self._turns[loop] = _Turns()
        return turns

    async def __call__(self, scope, receive, send) -> None:
        path = str(scope.get("path") or "")
        if (not (scope.get("type") == "http" and scope.get("method") == "GET" and path.startswith("/api/"))
                or path in UNQUEUED):
            await self.app(scope, receive, send)
            return
        turns = self._for_this_loop()
        if turns.stuck:                                    # a read is stuck: meanwhile nobody waits for a turn
            await self.app(scope, receive, send)
            return
        await turns.lock.acquire()
        held, ran_over = True, False

        def pass_the_turn() -> None:
            nonlocal held
            if held:
                held = False
                turns.lock.release()

        def too_long() -> None:
            nonlocal ran_over
            if held:
                ran_over = True
                turns.stuck += 1
                pass_the_turn()

        if turns.stuck:                                    # one got stuck while this read waited: it does not wait either
            pass_the_turn()
        timer = asyncio.get_running_loop().call_later(self.limit, too_long) if held else None

        async def send_and_pass_the_turn(message) -> None:
            if message.get("type") == "http.response.start":      # the view is worked out: the next read may start
                pass_the_turn()
            await send(message)

        try:
            await self.app(scope, receive, send_and_pass_the_turn)
        finally:
            if timer is not None:
                timer.cancel()
            pass_the_turn()                                # no answer went out (the request was dropped, or failed)
            if ran_over:
                turns.stuck -= 1


__all__ = ["LIMIT", "OneReadAtATime"]
