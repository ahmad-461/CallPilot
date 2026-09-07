from unittest.mock import patch, MagicMock
import pytest

from app.services.rag_service import (
    chunk_text,
    generate_embedding,
    store_document,
    search_knowledge_base,
    list_documents,
    delete_document,
    FALLBACK_QUERY,
)

TEST_BUSINESS_ID = "00000000-0000-0000-0000-000000000001"


def test_chunk_text():
    assert chunk_text("") == []
    assert chunk_text("   ") == []

    short = "Hello world!"
    assert chunk_text(short, chunk_size=100) == ["Hello world!"]

    long_text = "Word " * 200  # 1000 characters
    chunks = chunk_text(long_text, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_generate_embedding():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.embedding.values = [0.1] * 1536
    mock_client.models.embed_content.return_value = mock_response

    vector = generate_embedding("test text", client=mock_client)
    assert len(vector) == 1536
    assert vector[0] == 0.1
    mock_client.models.embed_content.assert_called_once()


@patch("app.services.rag_service.get_supabase_client")
@patch("app.services.rag_service.generate_embedding")
def test_store_document(mock_gen_embed, mock_get_supabase):
    mock_gen_embed.return_value = [0.0] * 1536
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_insert = MagicMock()
    mock_insert.execute.return_value.data = [{"created_at": "2025-01-01T00:00:00Z"}]
    mock_supabase.table.return_value.insert.return_value = mock_insert

    res = store_document(
        business_id=TEST_BUSINESS_ID,
        title="Services & Pricing",
        content="We offer haircuts and styling.",
    )

    assert res["success"] is True
    assert res["business_id"] == TEST_BUSINESS_ID
    assert res["title"] == "Services & Pricing"
    assert res["chunks_count"] == 1
    assert "document_id" in res


@patch("app.services.rag_service.get_supabase_client")
@patch("app.services.rag_service.generate_embedding")
def test_search_knowledge_base(mock_gen_embed, mock_get_supabase):
    mock_gen_embed.return_value = [0.0] * 1536
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.rpc.return_value.execute.return_value.data = [
        {"id": "chunk-1", "title": "Hours", "content": "Mon-Fri 9-5", "similarity": 0.85},
        {"id": "chunk-2", "title": "Services", "content": "Haircuts $50", "similarity": 0.25},
    ]

    results = search_knowledge_base(
        business_id=TEST_BUSINESS_ID,
        query="What are your hours?",
        similarity_threshold=0.3,
    )

    assert len(results) == 1
    assert results[0]["title"] == "Hours"
    assert results[0]["similarity"] == 0.85


@patch("app.services.rag_service.get_supabase_client")
@patch("app.services.rag_service.generate_embedding")
def test_search_knowledge_base_fallback_query(mock_gen_embed, mock_get_supabase):
    mock_gen_embed.return_value = [0.0] * 1536
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.rpc.return_value.execute.return_value.data = []

    search_knowledge_base(business_id=TEST_BUSINESS_ID, query="")

    # Verify generate_embedding was called with fallback query
    mock_gen_embed.assert_called_with(FALLBACK_QUERY, client=None)


@patch("app.services.rag_service.get_supabase_client")
def test_list_documents(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"document_id": "doc-1", "title": "FAQ Chunk 1", "created_at": "2025-01-01T00:00:00Z"},
        {"document_id": "doc-1", "title": "FAQ Chunk 2", "created_at": "2025-01-01T00:00:00Z"},
        {"document_id": "doc-2", "title": "Pricing", "created_at": "2025-01-02T00:00:00Z"},
    ]

    docs = list_documents(TEST_BUSINESS_ID)
    assert len(docs) == 2
    doc_ids = [d["id"] for d in docs]
    assert "doc-1" in doc_ids
    assert "doc-2" in doc_ids


@patch("app.services.rag_service.get_supabase_client")
def test_delete_document(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_delete = MagicMock()
    mock_delete.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "chunk-1"},
        {"id": "chunk-2"},
    ]
    mock_supabase.table.return_value.delete.return_value = mock_delete

    res = delete_document(TEST_BUSINESS_ID, "doc-1")
    assert res["success"] is True
    assert res["document_id"] == "doc-1"
    assert res["deleted_chunks_count"] == 2
