from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
TEST_BUSINESS_ID = "00000000-0000-0000-0000-000000000001"


@patch("app.routes.business.rag_service.store_document")
def test_upload_knowledge_base_document_success(mock_store):
    mock_store.return_value = {
        "success": True,
        "document_id": "doc-uuid-123",
        "title": "Business Hours & Services",
        "chunks_count": 2,
        "created_at": "2025-01-01T12:00:00Z",
    }

    payload = {
        "title": "Business Hours & Services",
        "content": "Our salon is open Monday through Friday from 9 AM to 6 PM.",
    }

    response = client.post(f"/business/{TEST_BUSINESS_ID}/knowledge-base", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["document_id"] == "doc-uuid-123"
    assert data["chunks_count"] == 2


def test_upload_knowledge_base_document_validation_error():
    # Empty title or content should return 422 Unprocessable Entity
    response = client.post(
        f"/business/{TEST_BUSINESS_ID}/knowledge-base",
        json={"title": "", "content": "Some content"},
    )
    assert response.status_code == 422


@patch("app.routes.business.rag_service.list_documents")
def test_list_knowledge_base_documents(mock_list):
    mock_list.return_value = [
        {"id": "doc-1", "title": "Hours & Location", "created_at": "2025-01-01T10:00:00Z"},
        {"id": "doc-2", "title": "Pricing Menu", "created_at": "2025-01-02T10:00:00Z"},
    ]

    response = client.get(f"/business/{TEST_BUSINESS_ID}/knowledge-base")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "doc-1"
    assert data[0]["title"] == "Hours & Location"


@patch("app.routes.business.rag_service.delete_document")
def test_delete_knowledge_base_document(mock_delete):
    mock_delete.return_value = {
        "success": True,
        "document_id": "doc-1",
        "business_id": TEST_BUSINESS_ID,
        "deleted_chunks_count": 3,
    }

    response = client.delete(f"/business/{TEST_BUSINESS_ID}/knowledge-base/doc-1")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["document_id"] == "doc-1"
    assert data["deleted_chunks_count"] == 3
