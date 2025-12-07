import os
import uuid
import json
import logging
from openai import OpenAI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel
from services.rabbit_publisher import RabbitPublisher
from services.rabbit_consumer import RabbitConsumer
from config import OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-mq")

app = FastAPI(title="LLM Streaming + RabbitMQ")

# CORS pour le client HTML
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],
)

# Client GLOBAL créé au démarrage
openai_client = OpenAI(api_key=OPENAI_API_KEY)
logger.info("OpenAI client created at startup")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/test", response_class=PlainTextResponse)
def test_openai():
    """Test OpenAI avec client global"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10
        )
        return f"OK: {response.choices[0].message.content}"
    except Exception as e:
        logger.error(f"Test Error: {e}", exc_info=True)
        return f"ERROR: {e}"


@app.post("/chat")
def chat(request: ChatRequest):
    """Chat avec streaming + RabbitMQ"""
    session_id = request.session_id or str(uuid.uuid4())
    
    def generate():
        publisher = RabbitPublisher(session_id)
        try:
            publisher.connect()
        except Exception as e:
            yield f"[ERROR: RabbitMQ - {e}]"
            return

        try:
            stream = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Tu es un assistant utile et concis."},
                    {"role": "user", "content": request.message}
                ],
                stream=True
            )

            full_response = ""
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_response += content
                    publisher.publish({"type": "chunk", "chunk": content})
                    yield content

            publisher.publish({"type": "complete"})
            logger.info(f"Session {session_id} done ({len(full_response)} chars)")

        except Exception as e:
            logger.error(f"Stream Error: {e}")
            publisher.publish({"type": "error", "error": str(e)})
            yield f"[ERROR: {e}]"
        finally:
            publisher.close()

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"X-Session-ID": session_id}
    )


@app.get("/stream/{session_id}")
async def stream_from_mq(session_id: str):
    """SSE depuis RabbitMQ"""
    async def events():
        consumer = RabbitConsumer(session_id)
        consumer.connect()
        try:
            async for chunk in consumer.consume_session():
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            consumer.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
