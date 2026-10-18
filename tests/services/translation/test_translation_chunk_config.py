from __future__ import annotations

import pytest

from anishift.services.translation.chunk_config import ChunkConfig
from anishift.services.translation.chunking import DEFAULT_CHAR_LIMIT, DEFAULT_CHUNK_LIMIT


def test_defaults_match_the_shipped_pipeline() -> None:
    assert ChunkConfig().chunk_chars == DEFAULT_CHAR_LIMIT


def test_the_default_chunk_size_keeps_the_shipped_piece_size() -> None:
    assert ChunkConfig().chunk_pieces == DEFAULT_CHUNK_LIMIT


@pytest.mark.parametrize(("chunk_chars", "pieces"), [(300, 100), (900, 300), (4000, 1333)])
def test_the_piece_size_follows_the_request_size(chunk_chars: int, pieces: int) -> None:
    assert ChunkConfig(chunk_chars=chunk_chars).chunk_pieces == pieces


def test_a_tiny_request_still_leaves_a_usable_piece() -> None:
    assert ChunkConfig(chunk_chars=1).chunk_pieces == 1


def test_a_request_size_that_cannot_produce_output_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ChunkConfig(chunk_chars=0)
