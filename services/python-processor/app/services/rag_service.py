from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.database import BrdDocument, ChatMessage
from app.models.schemas import ChatResponse, Citation
from app.services.vector_store import vector_store

BRD_SECTIONS = [
    ("executive_summary", "Executive Summary"),
    ("business_context", "Business Context and Objectives"),
    ("scope", "Scope (In Scope / Out of Scope)"),
    ("stakeholders", "Stakeholders"),
    ("functional_requirements", "Functional Requirements"),
    ("non_functional_requirements", "Non-Functional Requirements"),
    ("assumptions_constraints", "Assumptions and Constraints"),
    ("dependencies_risks", "Dependencies and Risks"),
    ("acceptance_criteria", "Acceptance Criteria"),
]

SYSTEM_PROMPT = """You are a BRD assistant. Use only the provided context from uploaded Excel files.
Rules:
- Cite sources using [file | sheet | cell_range] inline when making claims.
- If information is missing, explicitly say "Not found in uploaded files" and list gaps.
- Do not invent requirements.
- Be structured, concise, and professional.
"""


class RagService:
    def __init__(self) -> None:
        self._llm = None

    @property
    def llm(self):
        if self._llm is None and settings.anthropic_api_key:
            self._llm = ChatAnthropic(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
                temperature=0.2,
            )
        return self._llm

    def _llm_configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    def _format_context(self, results: list[dict]) -> tuple[str, list[Citation]]:
        if not results:
            return "No indexed content available.", []

        lines: list[str] = []
        citations: list[Citation] = []
        seen: set[str] = set()

        for idx, item in enumerate(results, start=1):
            meta = item["metadata"]
            source = f"{meta['file_name']} | {meta['sheet_name']} | {meta['cell_range']}"
            lines.append(f"[{idx}] Source: {source}\n{item['text']}")
            key = source
            if key not in seen:
                seen.add(key)
                citations.append(
                    Citation(
                        file=meta["file_name"],
                        sheet=meta["sheet_name"],
                        cell_range=meta["cell_range"],
                        excerpt=item["text"][:240],
                        score=round(float(item.get("score", 0)), 4),
                    )
                )
        return "\n\n".join(lines), citations

    def _confidence(self, results: list[dict]) -> str:
        if not results:
            return "low"
        top_score = float(results[0].get("score", 0))
        if top_score >= 0.55:
            return "high"
        if top_score >= 0.35:
            return "medium"
        return "low"

    def _gaps_from_answer(self, answer: str) -> list[str]:
        gaps: list[str] = []
        for line in answer.splitlines():
            lower = line.lower()
            if "not found in uploaded files" in lower or "missing" in lower:
                gaps.append(line.strip("- ").strip())
        return gaps[:5]

    def _invoke_llm(self, user_prompt: str) -> str:
        try:
            response = self.llm.invoke(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            return (
                "Claude API request failed. Please check your API key and model name in `.env`.\n\n"
                f"Configured model: `{settings.anthropic_model}`\n"
                f"Error: {exc}"
            )

    def answer_question(self, workspace_id: str, question: str) -> ChatResponse:
        results = vector_store.hybrid_search(workspace_id, question)
        context, citations = self._format_context(results)

        prompt = f"""Context from uploaded Excel files:
{context}

User question:
{question}

Provide a helpful answer with inline source citations.
"""
        if not self._llm_configured():
            answer = (
                "Claude API key is not configured. Retrieved context is available, "
                "but generation is disabled.\n\n" + context[:2000]
            )
            return ChatResponse(
                answer=answer,
                citations=citations,
                confidence=self._confidence(results),
                gaps=["LLM API key missing"] if not results else [],
            )

        answer = self._invoke_llm(prompt)
        return ChatResponse(
            answer=answer,
            citations=citations,
            confidence=self._confidence(results),
            gaps=self._gaps_from_answer(answer),
        )

    def generate_section(self, workspace_id: str, section_key: str, section_title: str) -> str:
        query = f"Generate content for BRD section: {section_title}. Include requirements, business rules, and details."
        results = vector_store.hybrid_search(workspace_id, query)
        context, _ = self._format_context(results)

        if not self._llm_configured():
            return (
                f"## {section_title}\n\n"
                "_Claude API key is not configured. Below is retrieved context only._\n\n"
                f"{context[:3000]}"
            )

        prompt = f"""Write the BRD section '{section_title}' using only this context:
{context}

Format in markdown with bullets and numbered requirements where appropriate.
Flag any missing information explicitly.
"""
        content = self._invoke_llm(prompt)
        return f"## {section_title}\n\n{content}"

    def generate_full_brd(self, db: Session, workspace_id: str, title: str) -> BrdDocument:
        sections: list[str] = [f"# {title}\n"]
        for section_key, section_title in BRD_SECTIONS:
            sections.append(self.generate_section(workspace_id, section_key, section_title))

        markdown = "\n\n".join(sections)
        existing_count = (
            db.query(BrdDocument).filter(BrdDocument.workspace_id == workspace_id).count()
        )
        document = BrdDocument(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            title=title,
            content_markdown=markdown,
            version=existing_count + 1,
            created_at=datetime.now(timezone.utc),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    def save_chat(
        self,
        db: Session,
        workspace_id: str,
        user_message: str,
        response: ChatResponse,
    ) -> None:
        db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                role="user",
                content=user_message,
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                role="assistant",
                content=response.answer,
                citations_json=json.dumps([c.model_dump() for c in response.citations]),
            )
        )
        db.commit()


rag_service = RagService()
