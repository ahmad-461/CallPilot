import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_EMBEDDING_DIM = 1536
FALLBACK_QUERY = "general business info hours services pricing location"


def get_gemini_client() -> genai.Client:
    """Initializes and returns the Gemini client using GEMINI_API_KEY env var."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable is not set!")
        api_key = os.getenv("LLM_API_KEY", "")

    return genai.Client(api_key=api_key)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Splits text into chunks of roughly chunk_size characters with overlap.
    Tries to break on whitespace/sentence boundaries when possible.
    """
    if not text or not text.strip():
        return []

    cleaned_text = text.strip()
    if len(cleaned_text) <= chunk_size:
        return [cleaned_text]

    chunks = []
    start = 0
    text_length = len(cleaned_text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        # If not at the end of the text, try to find a natural break (space or newline)
        if end < text_length:
            last_space = cleaned_text.rfind(" ", start + chunk_size // 2, end)
            if last_space != -1:
                end = last_space

        chunk = cleaned_text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start pointer forward considering overlap
        if end >= text_length:
            break
        start = max(start + 1, end - overlap)

    return chunks


def generate_embedding(
    text: str,
    client: Optional[genai.Client] = None,
    output_dimensionality: int = DEFAULT_EMBEDDING_DIM,
) -> List[float]:
    """
    Generates a vector embedding for a given text using Gemini API.
    Configured for 1536 output dimensionality to match PostgreSQL vector(1536).
    """
    if client is None:
        client = get_gemini_client()

    config = types.EmbedContentConfig(
        output_dimensionality=output_dimensionality,
    )

    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=config,
        )

        if response.embedding and response.embedding.values:
            return response.embedding.values
        raise ValueError("Gemini embedding response contained no vector values.")
    except Exception as e:
        logger.error(f"Failed to generate embedding for text: {e}")
        raise e


def store_document(
    business_id: str,
    title: str,
    content: str,
    client: Optional[genai.Client] = None,
) -> Dict[str, Any]:
    """
    Chunks document content, generates embeddings for each chunk, and stores them in knowledge_base_documents.
    Associates all chunks with a parent document_id UUID.
    """
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("Document content cannot be empty.")

    document_id = str(uuid.uuid4())
    supabase = get_supabase_client()

    rows_to_insert = []
    for chunk in chunks:
        embedding = generate_embedding(chunk, client=client)
        rows_to_insert.append(
            {
                "document_id": document_id,
                "business_id": business_id,
                "title": title,
                "content": chunk,
                "embedding": embedding,
            }
        )

    res = supabase.table("knowledge_base_documents").insert(rows_to_insert).execute()
    created_at = res.data[0]["created_at"] if res.data and len(res.data) > 0 else None

    return {
        "success": True,
        "document_id": document_id,
        "business_id": business_id,
        "title": title,
        "chunks_count": len(chunks),
        "created_at": created_at,
    }


def search_knowledge_base(
    business_id: str,
    query: Optional[str] = None,
    top_k: int = 3,
    similarity_threshold: float = 0.3,
    client: Optional[genai.Client] = None,
) -> List[Dict[str, Any]]:
    """
    Generates embedding for query (or fallback query if empty), calls match_knowledge_base RPC via Supabase,
    and returns top matching chunks above similarity_threshold (e.g. >= 0.3).
    """
    effective_query = query.strip() if (query and query.strip()) else FALLBACK_QUERY
    query_embedding = generate_embedding(effective_query, client=client)

    supabase = get_supabase_client()

    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": similarity_threshold,
        "match_count": top_k,
        "p_business_id": business_id,
    }

    response = supabase.rpc("match_knowledge_base", rpc_params).execute()
    results = response.data or []

    # Ensure results meet similarity threshold and are sorted by highest similarity
    filtered_results = [
        item for item in results
        if item.get("similarity", 0.0) >= similarity_threshold
    ]
    filtered_results.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)

    return filtered_results[:top_k]


def list_documents(business_id: str) -> List[Dict[str, Any]]:
    """
    Lists distinct documents stored for a business (aggregated by document_id).
    Returns id (document_id), title, and created_at.
    """
    supabase = get_supabase_client()

    response = (
        supabase.table("knowledge_base_documents")
        .select("document_id, title, created_at")
        .eq("business_id", business_id)
        .execute()
    )

    items = response.data or []

    # Aggregate by document_id
    docs_map: Dict[str, Dict[str, Any]] = {}
    for item in items:
        doc_id = item.get("document_id") or item.get("id")
        if not doc_id:
            continue
        if doc_id not in docs_map:
            docs_map[doc_id] = {
                "id": str(doc_id),
                "title": item.get("title", ""),
                "created_at": item.get("created_at"),
            }

    return list(docs_map.values())


def delete_document(business_id: str, document_id: str) -> Dict[str, Any]:
    """
    Deletes all knowledge base chunk rows sharing the parent document_id for a given business_id.
    """
    supabase = get_supabase_client()

    response = (
        supabase.table("knowledge_base_documents")
        .delete()
        .eq("business_id", business_id)
        .eq("document_id", document_id)
        .execute()
    )

    deleted_rows = response.data or []
    return {
        "success": True,
        "document_id": document_id,
        "business_id": business_id,
        "deleted_chunks_count": len(deleted_rows),
    }
