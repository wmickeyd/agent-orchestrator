from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from . import database, models, agent
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Agent Orchestrator")

# Initialize database
models.Base.metadata.create_all(bind=database.engine)

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    prompt: str
    attachments: Optional[List[dict]] = None
    config_override: Optional[dict] = None

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/v1/chat")
async def chat(request: ChatRequest, db: Session = Depends(database.get_db)):
    orchestrator = agent.AgentOrchestrator(db)
    
    async def event_generator():
        async for event in orchestrator.run(
            request.session_id,
            request.user_id,
            request.prompt,
            request.attachments,
            request.config_override
        ):
            yield {
                "event": event["event"],
                "data": event["data"]
            }

    return EventSourceResponse(event_generator())

@app.get("/v1/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(database.get_db)):
    history = db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id).all()
    return history

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
