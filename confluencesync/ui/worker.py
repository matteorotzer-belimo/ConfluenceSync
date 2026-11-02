"""Run blocking service calls in a background thread and hand the result back to the UI thread."""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..services import UserError

log = logging.getLogger(__name__)

# Tests set this to True: tasks then run immediately in the calling thread.
SYNC = False
_running: set["_Task"] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


def error_text(exc: Exception) -> str:
    if isinstance(exc, UserError):
        return str(exc)
    log.error("Unexpected error", exc_info=exc)
    return ("Etwas ist schiefgelaufen. Bitte nochmals versuchen. Wenn es wieder passiert, "
            "das Protokoll unter «Einstellungen» an den Support schicken.")


class _Task(QRunnable):
    def __init__(self, fn: Callable, args, kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - every error goes to the UI
            self.signals.failed.emit(error_text(exc))
        else:
            self.signals.done.emit(result)


def run_task(fn: Callable, *args, on_done: Callable | None = None, on_error: Callable | None = None,
             **kwargs) -> None:
    task = _Task(fn, args, kwargs)

    def finished(*_):
        _running.discard(task)

    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    task.signals.done.connect(finished)
    task.signals.failed.connect(finished)
    _running.add(task)
    if SYNC:
        task.run()
    else:
        QThreadPool.globalInstance().start(task)
