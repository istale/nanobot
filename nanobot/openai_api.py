from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nanobot.agent.loop import AgentLoop


class ChatMessage(BaseModel):
    role: str
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class OpenAICompatServer:
    """Minimal OpenAI-compatible facade for Open WebUI (intranet mode)."""

    def __init__(self, agent: AgentLoop, model_id: str = "nanobot-cdp"):
        self.agent = agent
        self.model_id = model_id

    def create_app(self) -> FastAPI:
        app = FastAPI(title="nanobot OpenAI API", version="0.1.0")

        @app.get("/health")
        def health() -> dict[str, Any]:
            return {"ok": True, "service": "nanobot-openai-api", "time": int(time.time())}

        @app.get("/v1/models")
        def models() -> dict[str, Any]:
            return {
                "object": "list",
                "data": [
                    {
                        "id": self.model_id,
                        "object": "model",
                        "created": 1700000000,
                        "owned_by": "nanobot-clean",
                    }
                ],
            }

        @app.post("/v1/chat/completions")
        async def chat_completions(req: ChatCompletionRequest) -> dict[str, Any]:
            user_message = None
            for msg in reversed(req.messages):
                if msg.role == "user" and msg.content.strip():
                    user_message = msg.content.strip()
                    break

            if not user_message:
                raise HTTPException(status_code=400, detail="No user message found")

            session_key = "openwebui:default"
            response_text = await self.agent.process_direct(
                user_message,
                session_key=session_key,
                channel="openwebui",
                chat_id="default",
            )

            now = int(time.time())
            completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            return {
                "id": completion_id,
                "object": "chat.completion",
                "created": now,
                "model": req.model or self.model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": response_text or ""},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

        return app


async def run_openai_api_server(
    *,
    agent: AgentLoop,
    host: str = "127.0.0.1",
    port: int = 18080,
    model_id: str = "nanobot-cdp",
) -> None:
    import uvicorn

    server = OpenAICompatServer(agent=agent, model_id=model_id)
    app = server.create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uvicorn_server = uvicorn.Server(config)
    await uvicorn_server.serve()
