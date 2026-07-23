"""
Mock execution backend — in-memory, deterministic, for tests.

``MockBackend`` records every ``invoke()`` call to ``self.calls`` and returns
either:
  - a pre-registered response (via :meth:`register_response`), or
  - a "dummy" instance constructed via ``output_model.model_construct(...)``
    with sensible defaults for primitive fields (str→"", int→0, list→[],
    nested models→recursively constructed).

If the model has a required field whose type we cannot safely fake (e.g.
``pydantic.HttpUrl`` with no default), :meth:`invoke` raises
``NotImplementedError`` telling the test author to register a fixture first.

This backend is the recommended substitute for the real Kilo CLI in unit
tests: it's deterministic, instantaneous, and has no side effects on the
filesystem.
"""

from __future__ import annotations

import inspect
import typing
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from pydantic import BaseModel, HttpUrl

# A sentinel for "we cannot build a safe dummy for this type".
_NO_DUMMY = object()


def _dummy_for_type(annotation: Any, depth: int = 0) -> Any:
    """Build a placeholder value for a type annotation.

    Returns ``_NO_DUMMY`` when no safe dummy exists (e.g. ``Any`` with no
    default, a non-BaseModel class we don't recognise).
    """
    if depth > 5:
        return _NO_DUMMY

    # Bare None / NoneType
    if annotation is type(None):
        return None

    # Origin-based generics (List[T], Dict[K,V], Optional[T], Union[A,B], ...)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[T] / Union[T, None] / Union[A, B]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _dummy_for_type(non_none[0], depth + 1)
        if len(non_none) > 1:
            # Heterogeneous union — try the first concrete type we can fake.
            for cand in non_none:
                dummy = _dummy_for_type(cand, depth + 1)
                if dummy is not _NO_DUMMY:
                    return dummy
        return None  # Union[..., None] already handled above

    # List[T] / Tuple[T, ...]
    if origin in (list, List):
        return []

    # Dict[K, V] / Mapping[K, V]
    if origin in (dict, Dict):
        return {}

    # Set[T]
    if origin in (set, frozenset):
        return []

    # Plain types
    if annotation is str:
        return ""
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is bool:
        return False
    if annotation is bytes:
        return b""
    if annotation is Any:
        return None  # Any defaults to None; only safe with optional fields
    if annotation is Path:
        return Path("/tmp/mock")
    if annotation is HttpUrl:
        # model_construct accepts any string for HttpUrl; it skips validation.
        return "https://example.com"

    # Pydantic models — recurse
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _construct_dummy(annotation, depth + 1)

    # Enums — use the first declared member's value (works for str-Enum and
    # plain Enum). model_construct accepts the raw value via duck-typing.
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return next(iter(annotation)).value
        except StopIteration:
            return _NO_DUMMY

    return _NO_DUMMY


def _construct_dummy(model: Type[BaseModel], depth: int = 0) -> BaseModel:
    """Construct a dummy instance of ``model`` using only field defaults +
    auto-generated placeholders for required fields.

    Raises ``NotImplementedError`` if a required field has no default and we
    cannot safely fake its type — the caller (a test) is expected to
    ``register_response(model, instance)`` first.
    """
    values: Dict[str, Any] = {}
    missing: List[str] = []

    for name, field in model.model_fields.items():
        # If the field has a default (including a default_factory), let
        # Pydantic fill it in — don't override.
        if field.is_required():
            dummy = _dummy_for_type(field.annotation, depth + 1)
            if dummy is _NO_DUMMY:
                missing.append(f"{name}: {field.annotation}")
            else:
                values[name] = dummy
        # else: Pydantic uses the field's default/default_factory automatically.

    if missing:
        raise NotImplementedError(
            f"MockBackend cannot auto-construct {model.__name__}: required "
            f"field(s) have no safe dummy ({', '.join(missing)}). Register "
            f"a fixture first via mock.register_response({model.__name__}, "
            f"instance)."
        )

    return model.model_construct(**values)


class MockBackend:
    """In-memory execution backend for tests.

    Usage::

        m = MockBackend()
        m.register_response(SiteUnderstanding, SiteUnderstanding(
            url="https://example.com",
            platform=PlatformType.WORDPRESS,
            ...
        ))
        result = m.invoke("scraper_specialist", "scrape ...", SiteUnderstanding)

    If no response is registered and the model has only "easy" required
    fields (str/int/float/bool/list/dict/Enum/HttpUrl/nested model), a
    dummy instance is returned automatically. Otherwise
    ``NotImplementedError`` is raised.

    The backend records every invocation in ``self.calls`` for assertion.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._responses: Dict[Type[BaseModel], BaseModel] = {}

    # -- registration -------------------------------------------------------

    def register_response(
        self,
        output_model: Type[BaseModel],
        instance: BaseModel,
    ) -> None:
        """Pre-program the response for calls to ``invoke(..., output_model)``.

        ``instance`` is returned verbatim (no validation, no copy). Tests
        typically pass a fully-constructed Pydantic instance here.
        """
        self._responses[output_model] = instance

    def clear_responses(self) -> None:
        """Forget all registered responses (handy between test cases)."""
        self._responses.clear()

    def clear_calls(self) -> None:
        """Forget the call log."""
        self.calls.clear()

    # -- ExecutionBackend protocol -----------------------------------------

    def invoke(
        self,
        persona: Union[str, Path],
        prompt: str,
        output_model: Type[BaseModel],
    ) -> BaseModel:
        """Return a registered response or build a dummy ``output_model``.

        Records the call in ``self.calls`` before delegating.
        """
        # Truncate very long prompts in the log to keep memory bounded.
        prompt_log = prompt if len(prompt) <= 2000 else prompt[:2000] + "...<truncated>"

        self.calls.append({
            "persona": str(persona),
            "prompt": prompt_log,
            "output_model": output_model.__name__,
        })

        if output_model in self._responses:
            return self._responses[output_model]

        return _construct_dummy(output_model)


__all__ = ["MockBackend"]
