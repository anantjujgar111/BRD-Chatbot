from __future__ import annotations

import json
import uuid
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from app.config import settings
from app.database import UploadedFile
from app.services.excel_extractor import ExtractedBlock, extract_excel_blocks


class VectorStoreService:
    def __init__(self) -> None:
        chroma_path = Path(settings.chroma_dir)
        chroma_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def _collection_name(self, workspace_id: str) -> str:
        return f"workspace_{workspace_id.replace('-', '_')}"

    def get_collection(self, workspace_id: str):
        return self.client.get_or_create_collection(
            name=self._collection_name(workspace_id),
            metadata={"hnsw:space": "cosine"},
        )

    def ingest_file(self, db: Session, file_record: UploadedFile) -> int:
        file_path = Path(file_record.stored_path)
        blocks = extract_excel_blocks(file_path, file_record.filename)
        if not blocks:
            file_record.status = "failed"
            file_record.error_message = "No readable content found in file."
            db.commit()
            return 0

        collection = self.get_collection(file_record.workspace_id)
        documents: list[str] = []
        metadatas: list[dict] = []
        ids: list[str] = []

        for block in blocks:
            chunks = self.splitter.split_text(block.text)
            for i, chunk in enumerate(chunks):
                chunk_id = f"{file_record.id}_{uuid.uuid4().hex[:12]}"
                documents.append(chunk)
                metadatas.append(
                    {
                        "file_name": block.file_name,
                        "sheet_name": block.sheet_name,
                        "cell_range": block.cell_range,
                        "block_type": block.block_type,
                        "file_id": file_record.id,
                    }
                )
                ids.append(chunk_id)

        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)

        file_record.status = "indexed"
        file_record.chunk_count = len(documents)
        file_record.error_message = None
        db.commit()
        return len(documents)

    def hybrid_search(
        self,
        workspace_id: str,
        query: str,
        top_k: int | None = None,
    ) -> list[dict]:
        top_k = top_k or settings.retrieval_top_k
        collection = self.get_collection(workspace_id)

        if collection.count() == 0:
            return []

        semantic_results = collection.query(
            query_texts=[query],
            n_results=min(top_k * 2, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        candidates: list[dict] = []
        docs = semantic_results.get("documents", [[]])[0]
        metas = semantic_results.get("metadatas", [[]])[0]
        distances = semantic_results.get("distances", [[]])[0]

        for doc, meta, distance in zip(docs, metas, distances):
            candidates.append(
                {
                    "text": doc,
                    "metadata": meta,
                    "semantic_score": 1 - float(distance),
                }
            )

        if not candidates:
            return []

        tokenized_corpus = [c["text"].lower().split() for c in candidates]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(query.lower().split())

        for candidate, bm25_score in zip(candidates, bm25_scores):
            candidate["keyword_score"] = float(bm25_score)
            candidate["score"] = (0.65 * candidate["semantic_score"]) + (
                0.35 * (bm25_score / (max(bm25_scores) + 1e-6))
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[: settings.rerank_top_k]

    def workspace_chunk_count(self, workspace_id: str) -> int:
        collection = self.get_collection(workspace_id)
        return collection.count()


vector_store = VectorStoreService()
