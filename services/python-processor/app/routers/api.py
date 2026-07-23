import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import UploadedFile, Workspace, get_db
from app.models.schemas import (
    BrdGenerateRequest,
    BrdResponse,
    ChatRequest,
    ChatResponse,
    FileResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)
from app.services.rag_service import BRD_SECTIONS, rag_service
from app.services.vector_store import vector_store

router = APIRouter()


def _ensure_paths() -> None:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_dir).mkdir(parents=True, exist_ok=True)


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "python-processor",
        "claude_configured": bool(settings.anthropic_api_key),
    }


@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    workspace = Workspace(
        id=str(uuid.uuid4()),
        name=payload.name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceResponse])
def list_workspaces(db: Session = Depends(get_db)):
    return db.query(Workspace).order_by(Workspace.created_at.desc()).all()


@router.get("/workspaces/{workspace_id}/files", response_model=list[FileResponse])
def list_files(workspace_id: str, db: Session = Depends(get_db)):
    return (
        db.query(UploadedFile)
        .filter(UploadedFile.workspace_id == workspace_id)
        .order_by(UploadedFile.created_at.desc())
        .all()
    )


@router.delete("/workspaces/{workspace_id}/files/{file_id}")
def delete_file(workspace_id: str, file_id: str, db: Session = Depends(get_db)):
    file_record = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == file_id, UploadedFile.workspace_id == workspace_id)
        .first()
    )
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    removed_chunks = vector_store.delete_file(workspace_id, file_id)

    stored_path = Path(file_record.stored_path)
    if stored_path.exists():
        stored_path.unlink()

    db.delete(file_record)
    db.commit()

    return {
        "message": "File removed from workspace context",
        "file_id": file_id,
        "filename": file_record.filename,
        "removed_chunks": removed_chunks,
        "remaining_chunk_count": vector_store.workspace_chunk_count(workspace_id),
    }


def _process_file(file_id: str) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        file_record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
        if not file_record:
            return
        file_record.status = "processing"
        db.commit()
        try:
            vector_store.ingest_file(db, file_record)
        except Exception as exc:
            file_record.status = "failed"
            file_record.error_message = str(exc)
            db.commit()
    finally:
        db.close()


@router.post("/workspaces/{workspace_id}/upload", response_model=list[FileResponse])
async def upload_files(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    _ensure_paths()
    workspace_dir = Path(settings.upload_dir) / workspace_id
    workspace_dir.mkdir(parents=True, exist_ok=True)

    created_files: list[UploadedFile] = []
    allowed = {".xlsx", ".xls", ".csv"}

    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in allowed:
            continue

        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}{suffix}"
        stored_path = workspace_dir / stored_name

        content = await upload.read()
        stored_path.write_bytes(content)

        file_record = UploadedFile(
            id=file_id,
            workspace_id=workspace_id,
            filename=upload.filename or stored_name,
            stored_path=str(stored_path.resolve()),
            status="queued",
        )
        db.add(file_record)
        created_files.append(file_record)

    db.commit()
    for file_record in created_files:
        db.refresh(file_record)
        background_tasks.add_task(_process_file, file_record.id)

    return created_files


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    workspace = db.query(Workspace).filter(Workspace.id == payload.workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        if payload.mode == "brd_section" and payload.section:
            section_map = {key: title for key, title in BRD_SECTIONS}
            section_title = section_map.get(payload.section, payload.section)
            answer = rag_service.generate_section(payload.workspace_id, payload.section, section_title)
            response = ChatResponse(answer=answer, citations=[], confidence="medium")
        elif payload.mode == "brd_full":
            document = rag_service.generate_full_brd(db, payload.workspace_id, "Business Requirements Document")
            response = ChatResponse(
                answer=document.content_markdown,
                citations=[],
                confidence="medium",
            )
        else:
            response = rag_service.answer_question(payload.workspace_id, payload.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {exc}") from exc

    rag_service.save_chat(db, payload.workspace_id, payload.message, response)
    return response


@router.post("/brd/generate", response_model=BrdResponse)
def generate_brd(payload: BrdGenerateRequest, db: Session = Depends(get_db)):
    workspace = db.query(Workspace).filter(Workspace.id == payload.workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    document = rag_service.generate_full_brd(db, payload.workspace_id, payload.title)
    return document


@router.get("/workspaces/{workspace_id}/brd", response_model=list[BrdResponse])
def list_brd_documents(workspace_id: str, db: Session = Depends(get_db)):
    from app.database import BrdDocument

    return (
        db.query(BrdDocument)
        .filter(BrdDocument.workspace_id == workspace_id)
        .order_by(BrdDocument.created_at.desc())
        .all()
    )


@router.get("/workspaces/{workspace_id}/stats")
def workspace_stats(workspace_id: str, db: Session = Depends(get_db)):
    files = db.query(UploadedFile).filter(UploadedFile.workspace_id == workspace_id).all()
    indexed = sum(1 for f in files if f.status == "indexed")
    return {
        "file_count": len(files),
        "indexed_files": indexed,
        "chunk_count": vector_store.workspace_chunk_count(workspace_id),
    }
