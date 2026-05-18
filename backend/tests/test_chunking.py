import pytest

from app.services.ingestion import _chunk_text, _count_tokens


class TestTokenCounting:
    def test_empty_string(self):
        assert _count_tokens("") == 0

    def test_single_word(self):
        assert _count_tokens("hello") > 0

    def test_consistent_count(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert _count_tokens(text) == _count_tokens(text)


class TestChunking:
    def test_short_text_single_chunk(self):
        text = "This is a short HR policy statement about vacation days."
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        # Generate text longer than chunk_size tokens
        paragraph = "Employees are entitled to paid time off as outlined in the company policy. "
        long_text = paragraph * 50
        chunks = _chunk_text(long_text, chunk_size=200, overlap=20)
        assert len(chunks) > 1

    def test_chunks_non_empty(self):
        paragraph = "This is a test sentence for the HR policy chunking algorithm. "
        long_text = paragraph * 30
        chunks = _chunk_text(long_text, chunk_size=100, overlap=10)
        for chunk in chunks:
            assert chunk.strip() != ""

    def test_chunks_cover_content(self):
        text = "Section A: vacation policy. Section B: health benefits. Section C: remote work guidelines."
        chunks = _chunk_text(text, chunk_size=10, overlap=2)
        combined = " ".join(chunks)
        assert "vacation" in combined
        assert "health" in combined

    def test_overlap_creates_continuity(self):
        paragraph = "The quick brown fox jumps over the lazy dog. " * 20
        chunks_no_overlap = _chunk_text(paragraph, chunk_size=50, overlap=0)
        chunks_with_overlap = _chunk_text(paragraph, chunk_size=50, overlap=10)
        # Overlap should produce more or equal chunks
        assert len(chunks_with_overlap) >= len(chunks_no_overlap)

    def test_empty_text_returns_empty(self):
        chunks = _chunk_text("", chunk_size=512, overlap=64)
        assert chunks == []

    def test_whitespace_only_returns_empty(self):
        chunks = _chunk_text("   \n\n   \t  ", chunk_size=512, overlap=64)
        assert chunks == []

    def test_chunk_size_respected(self):
        paragraph = "word " * 1000
        chunks = _chunk_text(paragraph, chunk_size=100, overlap=10)
        for chunk in chunks:
            token_count = _count_tokens(chunk)
            # Allow 10% tolerance for separator adjustments
            assert token_count <= 110, f"Chunk too large: {token_count} tokens"
