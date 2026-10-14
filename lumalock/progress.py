"""Optional observers must never interrupt a hardware transaction."""


def emit(callback, stage, message, completed=None, total=None, **details):
    if callback is None:
        return
    event = dict(stage=stage, message=message, completed=completed, total=total, **details)
    try:
        callback(event)
    except Exception:
        # A presentation failure must not skip verification or recovery.
        pass
