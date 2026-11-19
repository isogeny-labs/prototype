"""One read at a time.

A page asks for several views at once: its own, the Related block of an open item, the Otto panel's. Each view is
worked out from many small database reads, and Python works several of them out side by side much more slowly than one
after another: the same twelve views took about 3 seconds in a row and about 7 seconds when six were worked out at once
(measured on 19 November 2026, on four cores). With the Otto panel beside every page that turned a quick walk through
the pages into a queue, and the Overview's own numbers arrived seconds late.

So the reads under /api take turns, in the order they arrived: the page's own reads first, the panel's after them. A
turn ends when the answer starts to go out, so a slow download holds nobody back. A request that changes something
(anything that is not a GET) takes no turn and waits for none: a check that talks to a server, or a file being brought
in, never stops the pages from reading. Nothing is decided here, and no answer is changed.
"""
from __future__ import annotations

import asyncio
import weakref


class OneReadAtATime:
    """Web middleware: GET requests under /api are answered one after another, first come, first served."""

    def __init__(self, app) -> None:
        self.app = app
        # (one lock for each event loop: the app has one, and every test client brings its own)
        self._locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()

    def _lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._locks.get(loop)
        if lock is None:
            lock = self._locks[loop] = asyncio.Lock()
        return lock

    async def __call__(self, scope, receive, send) -> None:
        if not (scope.get("type") == "http" and scope.get("method") == "GET" and str(scope.get("path") or "").startswith("/api/")):
            await self.app(scope, receive, send)
            return
        lock = self._lock()
        await lock.acquire()
        held = True

        async def send_and_pass_the_turn(message) -> None:
            nonlocal held
            if held and message.get("type") == "http.response.start":      # the view is worked out: the next read may start
                held = False
                lock.release()
            await send(message)

        try:
            await self.app(scope, receive, send_and_pass_the_turn)
        finally:
            if held:                                                        # no answer went out (the request was dropped, or failed)
                held = False
                lock.release()


__all__ = ["OneReadAtATime"]
