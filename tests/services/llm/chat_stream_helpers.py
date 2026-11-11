from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace, TracebackType


@dataclass(slots=True)
class FakeChatStream:
    chunks: tuple[object, ...]
    error: BaseException | None = None
    closed: bool = field(default=False, init=False)

    def __enter__(self) -> FakeChatStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.closed = True

    def __iter__(self) -> Iterator[object]:
        yield from self.chunks
        if self.error is not None:
            raise self.error


def chat_chunk(
    *,
    content: str | None = None,
    refusal: str | None = None,
    finish_reason: object = None,
    model: str = "custom-model",
) -> object:
    delta = SimpleNamespace(role="assistant", content=content, refusal=refusal)
    return SimpleNamespace(
        choices=[SimpleNamespace(index=0, delta=delta, finish_reason=finish_reason)], model=model, usage=None
    )


def chat_stream(  # noqa: PLR0913
    *,
    text: str | None = "translated",
    finish_reason: object = "stop",
    model: str = "custom-model",
    usage: object = None,
    refusal: str | None = None,
    error: BaseException | None = None,
) -> FakeChatStream:
    pieces: list[str] = (text or "").splitlines(keepends=True)
    chunks: list[object] = [chat_chunk(content=None, model=model)]
    chunks.extend(chat_chunk(content=piece, model=model) for piece in pieces)
    chunks.append(chat_chunk(refusal=refusal, finish_reason=finish_reason, model=model))
    chunks.append(SimpleNamespace(choices=[], model=model, usage=usage))
    return FakeChatStream(tuple(chunks), error)
