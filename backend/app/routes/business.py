import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/business", tags=["business"])


class KnowledgeBaseUploadRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Document title")
    content: str = Field(..., min_length=1, description="Raw document text content")


class KnowledgeBaseDocumentResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None


class KnowledgeBaseUploadResponse(BaseModel):
    success: bool
    document_id: str
    title: str
    chunks_count: int
    created_at: Optional[str] = None


class KnowledgeBaseDeleteResponse(BaseModel):
    success: bool
    document_id: str
    deleted_chunks_count: int


# TODO: Add admin JWT authentication dependency in a future phase
@router.post(
    "/{business_id}/knowledge-base",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeBaseUploadResponse,
)
async def upload_knowledge_base_document(
    business_id: str,
    payload: KnowledgeBaseUploadRequest,
):
    """
    Uploads a document to the business knowledge base.
    Chunks text content, generates vector embeddings via Gemini, and stores chunks.
    Unauthenticated endpoint for Phase 4 (admin auth coming in later phase).
    """
    try:
        res = rag_service.store_document(
            business_id=business_id,
            title=payload.title,
            content=payload.content,
        )
        return KnowledgeBaseUploadResponse(
            success=True,
            document_id=res["document_id"],
            title=res["title"],
            chunks_count=res["chunks_count"],
            created_at=str(res["created_at"]) if res.get("created_at") else None,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to store knowledge base document for business {business_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store document: {str(e)}",
        )


# TODO: Add admin JWT authentication dependency in a future phase
@router.get(
    "/{business_id}/knowledge-base",
    status_code=status.HTTP_200_OK,
    response_model=List[KnowledgeBaseDocumentResponse],
)
async def list_knowledge_base_documents(business_id: str):
    """
    Lists stored knowledge base documents for a business.
    Returns metadata list (id, title, created_at) without full content or embeddings.
    """
    try:
        docs = rag_service.list_documents(business_id=business_id)
        return [
            KnowledgeBaseDocumentResponse(
                id=doc["id"],
                title=doc["title"],
                created_at=str(doc["created_at"]) if doc.get("created_at") else None,
            )
            for doc in docs
        ]
    except Exception as e:
        logger.error(f"Failed to list knowledge base documents for business {business_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}",
        )


# TODO: Add admin JWT authentication dependency in a future phase
@router.delete(
    "/{business_id}/knowledge-base/{document_id}",
    status_code=status.HTTP_200_OK,
    response_model=KnowledgeBaseDeleteResponse,
)
async def delete_knowledge_base_document(business_id: str, document_id: str):
    """
    Deletes all chunk rows belonging to a knowledge base document for a business.
    """
    try:
        res = rag_service.delete_document(
            business_id=business_id,
            document_id=document_id,
        )
        return KnowledgeBaseDeleteResponse(
            success=True,
            document_id=res["document_id"],
            deleted_chunks_count=res["deleted_chunks_count"],
        )
    except Exception as e:
        logger.error(f"Failed to delete document {document_id} for business {business_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}",
        )
