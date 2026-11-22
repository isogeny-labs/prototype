"""Sandbox research (a prototype for Isogeny's own sandbox; Kevin's plan and decisions of 22 November 2026,
`docs/plans/otto-auto-researcher-change-watch.md`).

Everything in this package sits behind one switch in Settings, which is off by default and can be turned on only on a
computer marked as the sandbox. With the switch off the app behaves exactly as it did before this package existed.

  state.py       the switch, its second tick and its spending limits (mixed into Lab)
"""
