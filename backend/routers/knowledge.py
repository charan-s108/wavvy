"""
/api/kb — Knowledge Base REST endpoints.

POST   /api/kb/upload               — single multipart upload
POST   /api/kb/upload-batch         — multiple files, one BG task each
GET    /api/kb/documents            — list all documents
DELETE /api/kb/documents/{doc_id}   — remove document + all chunks
GET    /api/kb/search?q=&n=5        — hybrid search with retrieval badges + RRF score
GET    /api/kb/status/{doc_id}      — chunk count + status
GET    /api/kb/chunks/{doc_id}      — sorted chunk list with token counts
GET    /api/kb/similarity/{doc_id}  — N×N cosine similarity matrix
GET    /api/kb/questions/{doc_id}   — suggested questions from doc headings
"""
import os
import uuid
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from pydantic import BaseModel
from sqlalchemy import text

from database import AsyncSessionLocal
from knowledge import kb_manager, embeddings as embeddings_module

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb", tags=["knowledge"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


# ── Pydantic models ───────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    message: str


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    category: str
    chunk_count: int
    status: str


class SearchResult(BaseModel):
    content: str
    source: str
    relevance: float
    category: str
    retrieval: str = "dense"   # "dense" | "bm25" | "graph" | "hybrid"
    rrf_score: float = 0.0


# ── Shared ingest helper ──────────────────────────────────────────────────────

def _validate_file(filename: str, size: int) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
    return suffix


async def _accept_file(
    file: UploadFile,
    category: str,
    background_tasks: BackgroundTasks,
) -> UploadResponse:
    filename = file.filename or "unknown"
    contents = await file.read()
    suffix = _validate_file(filename, len(contents))
    doc_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""INSERT INTO kb_documents (id, filename, file_type, category, status)
                         VALUES (:id, :fn, :ft, :cat, 'processing')"""),
                {"id": uuid.UUID(doc_id), "fn": filename, "ft": suffix.lstrip("."), "cat": category},
            )
            await db.commit()
    except Exception as exc:
        os.unlink(tmp_path)
        logger.error(f"KB DB insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Database error")

    background_tasks.add_task(
        _ingest_background, tmp_path, doc_id, filename, suffix.lstrip("."), category
    )
    return UploadResponse(
        doc_id=doc_id,
        filename=filename,
        status="processing",
        message="Document accepted. Indexing in background.",
    )


async def _ingest_background(
    tmp_path: str,
    doc_id: str,
    filename: str,
    file_type: str,
    category: str,
) -> None:
    try:
        _, chunk_count = await kb_manager.ingest_document(
            file_path=tmp_path,
            filename=filename,
            file_type=file_type,
            category=category,
            doc_id=doc_id,
        )
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE kb_documents SET status='ready', chunk_count=:cc WHERE id=:id"),
                {"cc": chunk_count, "id": uuid.UUID(doc_id)},
            )
            await db.commit()
        logger.info(f"KB doc {doc_id} ready with {chunk_count} chunks")
    except Exception as exc:
        logger.error(f"Ingestion failed for {doc_id}: {exc}")
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("UPDATE kb_documents SET status='error' WHERE id=:id"),
                    {"id": uuid.UUID(doc_id)},
                )
                await db.commit()
        except Exception:
            pass
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── Upload (single) ───────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(default="general"),
):
    return await _accept_file(file, category, background_tasks)


# ── Upload (batch) ────────────────────────────────────────────────────────────

@router.post("/upload-batch", response_model=list[UploadResponse])
async def upload_batch(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    category: str = Form(default="general"),
):
    responses = []
    for file in files:
        resp = await _accept_file(file, category, background_tasks)
        responses.append(resp)
    return responses


# ── List documents ────────────────────────────────────────────────────────────

@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT id, filename, file_type, category, chunk_count, status "
                 "FROM kb_documents ORDER BY uploaded_at DESC")
        )
        rows = result.mappings().all()

    return [
        DocumentInfo(
            doc_id=str(row["id"]),
            filename=row["filename"],
            file_type=row["file_type"] or "",
            category=row["category"] or "general",
            chunk_count=row["chunk_count"] or 0,
            status=row["status"] or "unknown",
        )
        for row in rows
    ]


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    deleted = await kb_manager.delete_document(doc_id)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM kb_documents WHERE id=:id"),
            {"id": uuid.UUID(doc_id)},
        )
        await db.commit()
    return {"deleted": True, "chunks_removed": deleted, "doc_id": doc_id}


# ── Search (hybrid) ───────────────────────────────────────────────────────────

@router.get("/search", response_model=list[SearchResult])
async def search_kb(q: str, n: int = 3):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    hits = await kb_manager.search_kb(q.strip(), n_results=min(n, 10))
    return [
        SearchResult(
            content=h["content"],
            source=h["source"],
            relevance=h.get("relevance", h.get("rrf_score", 0.0)),
            category=h.get("category", "general"),
            retrieval=h.get("retrieval", "dense"),
            rrf_score=h.get("rrf_score", 0.0),
        )
        for h in hits
    ]


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status/{doc_id}")
async def document_status(doc_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT filename, status, chunk_count FROM kb_documents WHERE id=:id"),
            {"id": uuid.UUID(doc_id)},
        )
        row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "doc_id": doc_id,
        "filename": row["filename"],
        "status": row["status"],
        "chunk_count": row["chunk_count"] or 0,
    }


# ── Inspector endpoints ───────────────────────────────────────────────────────

@router.get("/chunks/{doc_id}")
async def get_chunks(doc_id: str):
    chunks = kb_manager.get_doc_chunks(doc_id)
    if not chunks:
        # Verify the doc exists in DB before returning 404
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT id FROM kb_documents WHERE id=:id"),
                {"id": uuid.UUID(doc_id)},
            )
            if not result.first():
                raise HTTPException(status_code=404, detail="Document not found")
    return chunks


@router.get("/similarity/{doc_id}")
async def get_similarity(doc_id: str):
    return kb_manager.get_chunk_similarity(doc_id)


@router.get("/questions/{doc_id}")
async def get_questions(doc_id: str):
    return kb_manager.get_suggested_questions(doc_id)


@router.post("/rebuild-index")
async def rebuild_index():
    """Rebuild BM25 + entity indexes in-process without restarting the server."""
    kb_manager._rebuild_indexes()
    ei = len(kb_manager._entity_index)
    ep = len(kb_manager._entity_pair_index)
    chunks = len(kb_manager._bm25_corpus)
    return {"chunks": chunks, "entities": ei, "entity_pairs": ep}
