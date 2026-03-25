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

class UserUpdate(BaseModel):
    preferred_model: Optional[str] = None
    preferred_temp_unit: Optional[str] = None
    preferred_lang: Optional[str] = None
    timezone: Optional[str] = None

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

@app.get("/v1/users/{user_id}")
def get_user_profile(user_id: str, db: Session = Depends(database.get_db)):
    profile = db.query(models.UserProfile).filter(models.UserProfile.user_id == user_id).first()
    if not profile:
        return {"user_id": user_id, "preferred_model": "gemma3n:e4b", "preferred_temp_unit": "Celsius", "preferred_lang": "en"}
    return profile

@app.patch("/v1/users/{user_id}")
def update_user_profile(user_id: str, update: UserUpdate, db: Session = Depends(database.get_db)):
    profile = db.query(models.UserProfile).filter(models.UserProfile.user_id == user_id).first()
    if not profile:
        profile = models.UserProfile(user_id=user_id)
        db.add(profile)
    
    if update.preferred_model is not None: profile.preferred_model = update.preferred_model
    if update.preferred_temp_unit is not None: profile.preferred_temp_unit = update.preferred_temp_unit
    if update.preferred_lang is not None: profile.preferred_lang = update.preferred_lang
    if update.timezone is not None: profile.timezone = update.timezone
    
    db.commit()
    db.refresh(profile)
    return profile

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
