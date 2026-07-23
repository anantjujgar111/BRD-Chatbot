from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = "Default Workspace"


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    created_at: datetime


class FileResponse(BaseModel):
    id: str
    workspace_id: str
    filename: str
    status: str
    error_message: str | None = None
    chunk_count: int = 0
    created_at: datetime


class ChatRequest(BaseModel):
    workspace_id: str
    message: str
    mode: Literal["qa", "brd_full", "brd_section"] = "qa"
    section: str | None = None


class Citation(BaseModel):
    file: str
    sheet: str
    cell_range: str
    excerpt: str
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    gaps: list[str] = Field(default_factory=list)


class BrdGenerateRequest(BaseModel):
    workspace_id: str
    title: str = "Business Requirements Document"


class BrdResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    content_markdown: str
    version: int
    created_at: datetime
