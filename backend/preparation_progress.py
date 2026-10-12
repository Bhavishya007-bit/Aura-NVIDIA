"""Optional per-job progress hooks; ordinary calls remain unchanged."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

_callback: ContextVar[Callable | None] = ContextVar('aura_preparation_callback', default=None)
_span: ContextVar[tuple[int, int] | None] = ContextVar('aura_embedding_span', default=None)

def report(stage: str, completed: int = 0, total: int = 0):
    callback = _callback.get()
    if callback:
        callback(stage, completed, total)

@contextmanager
def preparation_progress(callback):
    token = _callback.set(callback)
    try:
        yield
    finally:
        _callback.reset(token)

@contextmanager
def embedding_span(offset: int, total: int):
    token = _span.set((offset, total))
    try:
        yield
    finally:
        _span.reset(token)

def encoded(completed: int):
    span = _span.get()
    if span:
        report('indexing', span[0] + completed, span[1])
