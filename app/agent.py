import json
import logging
import aiohttp
import asyncio
from datetime import datetime, timezone
from . import config, models, database

logger = logging.getLogger(__name__)

# Re-use your tool definitions (Shortened for brevity here)
TOOLS = [
    {"type": "function", "function": {"name": "search_web", "description": "Search the web...", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_weather", "description": "Get weather...", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}},
    # ... add others from llm.py
]

async def call_ollama_chat(messages, model, tools=None):
    """Low-level Ollama API caller."""
    url = config.OLLAMA_URL.replace("/generate", "/chat")
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "tools": tools or []
    }
    
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                error = await response.text()
                raise Exception(f"Ollama error: {response.status} - {error}")
            
            async for line in response.content:
                if line:
                    yield json.loads(line.decode('utf-8'))

class AgentOrchestrator:
    def __init__(self, db_session):
        self.db = db_session

    async def run(self, session_id, user_id, prompt, attachments=None, config_override=None):
        """Main Agent Loop yielding SSE events."""
        
        # 1. Setup Context
        model = config_override.get("model") if config_override else None
        if not model:
            profile = self.db.query(models.UserProfile).filter(models.UserProfile.user_id == user_id).first()
            model = profile.preferred_model if profile else config.OLLAMA_MODEL

        messages = self._assemble_messages(session_id, prompt, attachments)
        
        # 2. Multi-turn Agent Loop (Max 3 turns for safety)
        for turn in range(3):
            yield {"event": "status", "data": {"state": "thinking", "turn": turn + 1}}
            
            full_response_content = ""
            tool_calls = []
            
            try:
                async for chunk in call_ollama_chat(messages, model, tools=TOOLS if turn == 0 else []):
                    msg_chunk = chunk.get('message', {})
                    
                    # Handle Tool Calls
                    if msg_chunk.get('tool_calls'):
                        tool_calls.extend(msg_chunk['tool_calls'])
                        continue
                    
                    # Handle Content
                    content = msg_chunk.get('content', '')
                    if content:
                        full_response_content += content
                        yield {"event": "content", "data": {"delta": content}}
                    
                    if chunk.get('done'):
                        break
                
                if tool_calls:
                    yield {"event": "status", "data": {"state": "calling_tool"}}
                    messages.append({"role": "assistant", "tool_calls": tool_calls})
                    
                    for call in tool_calls:
                        result = await self._execute_tool(call['function']['name'], call['function']['arguments'])
                        yield {"event": "tool_result", "data": {"tool": call['function']['name'], "output": result}}
                        messages.append({"role": "tool", "content": str(result), "tool_call_id": call.get('id', 'fixed_id')})
                    
                    # Continue to next turn to let LLM process tool results
                    continue
                
                # If no tool calls, we are done
                yield {"event": "final_answer", "data": {"content": full_response_content}}
                self._save_history(session_id, prompt, full_response_content)
                break

            except Exception as e:
                logger.error(f"Agent Loop Error: {e}")
                yield {"event": "error", "data": {"message": str(e)}}
                break

    def _assemble_messages(self, session_id, prompt, attachments):
        # Implementation of history retrieval + current prompt
        messages = [{"role": "system", "content": "You are a helpful assistant..."}]
        
        history = self.db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id).order_by(models.ChatMessage.timestamp.desc()).limit(10).all()
        for msg in reversed(history):
            messages.append({"role": msg.role, "content": msg.content})
            
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _execute_tool(self, name, args):
        # Logic to call utility-api / webscraper
        return f"Result of {name} is placeholder"

    def _save_history(self, session_id, prompt, response):
        user_msg = models.ChatMessage(session_id=session_id, role="user", content=prompt)
        asst_msg = models.ChatMessage(session_id=session_id, role="assistant", content=response)
        self.db.add(user_msg)
        self.db.add(asst_msg)
        self.db.commit()
