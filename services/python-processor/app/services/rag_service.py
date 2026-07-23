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

SYSTEM_PROMPT = """You are a BRD assistant. Use the provided context from uploaded Excel files.
Rules:
- Cite sources using [file | sheet | cell_range] inline when making claims.
- If information is missing, explicitly say "Not found in uploaded files" and list gaps.
- Do not invent requirements.
- Be structured, concise, and professional.
- You may see prior messages in this session. Use them for follow-up questions like "summarize that" or "compare those".
- Factual claims must still be grounded in the uploaded file context provided with each turn.
"""


class RagService:
    def __init__(self) -> None:
        self._llm = None

    @property
    def llm(self):
        if self._llm is None and settings.anthropic_api_key:
            self._llm = self._build_llm(settings.anthropic_model)
        return self._llm

    def _model_candidates(self) -> list[str]:
        configured = [settings.anthropic_model]
        fallbacks = [
            model.strip()
            for model in settings.anthropic_fallback_models.split(",")
            if model.strip()
        ]
        models: list[str] = []
        for model in configured + fallbacks:
            if model not in models:
                models.append(model)
        return models

    def _build_llm(self, model_name: str):
        return ChatAnthropic(
            api_key=settings.anthropic_api_key,
            model=model_name,
            temperature=0.2,
        )

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

    def _load_chat_history(self, db: Session, workspace_id: str) -> list[dict]:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.workspace_id == workspace_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(settings.chat_history_limit)
            .all()
        )
        messages.reverse()
        return [{"role": message.role, "content": message.content} for message in messages]

    def _build_search_query(self, question: str, history: list[dict]) -> str:
        recent_user_messages = [
            message["content"] for message in history if message["role"] == "user"
        ][-2:]
        return " ".join([*recent_user_messages, question]).strip()

    def _invoke_llm(self, user_prompt: str, history: list[dict] | None = None) -> str:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for message in history or []:
            if message["role"] in {"user", "assistant"}:
                messages.append(
                    {
                        "role": message["role"],
                        "content": message["content"][:4000],
                    }
                )
        messages.append({"role": "user", "content": user_prompt})
        errors: list[str] = []

        for model_name in self._model_candidates():
            try:
                response = self._build_llm(model_name).invoke(messages)
                content = response.content if hasattr(response, "content") else str(response)
                if model_name != settings.anthropic_model:
                    content = (
                        f"_Note: fallback model `{model_name}` was used because "
                        f"`{settings.anthropic_model}` is not available on your API key._\n\n"
                        f"{content}"
                    )
                self._llm = self._build_llm(model_name)
                return content
            except Exception as exc:
                errors.append(f"{model_name}: {exc}")

        return (
            "Claude API request failed for all configured models. "
            "Update `ANTHROPIC_MODEL` in `.env` and restart the Python service.\n\n"
            + "\n".join(errors[:3])
        )

    def answer_question(self, db: Session, workspace_id: str, question: str) -> ChatResponse:
        history = self._load_chat_history(db, workspace_id)
        search_query = self._build_search_query(question, history)
        results = vector_store.hybrid_search(workspace_id, search_query)
        context, citations = self._format_context(results)

        prompt = f"""Context from uploaded Excel files:
{context}

User question:
{question}

Provide a helpful answer with inline source citations.
Use the conversation history when the user asks follow-up questions.
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

        answer = self._invoke_llm(prompt, history=history)
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
