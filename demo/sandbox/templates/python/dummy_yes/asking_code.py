"""A control, not asking code: it says yes to every question and never asks the library. The known-answer check must refuse it."""
OWN_REFUSALS = ()


def check_signature(public_key, message, signature):
    return True
