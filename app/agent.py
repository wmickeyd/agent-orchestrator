import json
import logging
import aiohttp
import asyncio
from datetime import datetime, timezone
from . import config, models, database

logger = logging.getLogger(__name__)

# Full tool definitions
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for real-time news, general knowledge, or specific facts.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current real-time weather for a specific location.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string", "description": "The city, state, or zip code."}},
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Read and summarize the text content of a specific website URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The full URL to read."}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_crypto_price",
            "description": "Get the real-time price of a stock (e.g. AAPL) or crypto (e.g. BTC-USD).",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "The ticker symbol."}},
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_lego_set",
            "description": "Start tracking the price of a LEGO set from a LEGO.com URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The LEGO.com product URL."}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_images",
            "description": "Search the web for images.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The image search query."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Get latest news headlines for a specific topic.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The news topic to search for."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_reddit",
            "description": "Read and summarize a Reddit thread and its top comments from a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The full Reddit thread URL."}},
                "required": ["url"]
            }
        }
    }
]

async def call_ollama_chat(messages, model, tools=None):
    """Low-level Ollama API caller."""
    url = config.OLLAMA_URL.replace("/generate", "/chat")
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "tools": tools or [],
        "options": {
            "num_ctx": 2048,
            "num_predict": 512,
        }
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
        logger.info(f"AgentOrchestrator.run started for session {session_id}")
        
        # 1. Setup Context
        model = config_override.get("model") if config_override else None
        if not model:
            profile = self.db.query(models.UserProfile).filter(models.UserProfile.user_id == user_id).first()
            model = profile.preferred_model if profile else config.OLLAMA_MODEL

        logger.info(f"Using model: {model} for session {session_id}")
        messages = self._assemble_messages(session_id, prompt, attachments)
        logger.info(f"Assembled context: {len(messages)} messages")
        
        # Optimization: Skip tools for very simple greetings/short queries
        is_simple = len(prompt.strip()) < 15 and not any(w in prompt.lower() for w in ["weather", "stock", "search", "news", "track", "price"])
        active_tools = [] if is_simple else TOOLS
        logger.info(f"Simple query detection: {is_simple} (Tools: {len(active_tools)})")

        # 2. Multi-turn Agent Loop (Max 3 turns for safety)
        for turn in range(3):
            logger.info(f"Starting Turn {turn+1} for session {session_id}")
            yield {"event": "status", "data": {"state": "thinking", "turn": turn + 1}}
            
            full_response_content = ""
            tool_calls = []
            
            try:
                # Use current tools (only on first turn usually)
                current_tools = active_tools if turn == 0 else []
                
                async def do_request(use_tools):
                    nonlocal full_response_content
                    async for chunk in call_ollama_chat(messages, model, tools=use_tools):
                        msg_chunk = chunk.get('message', {})
                        if msg_chunk.get('tool_calls'):
                            tool_calls.extend(msg_chunk['tool_calls'])
                            continue
                        content = msg_chunk.get('content', '')
                        if content:
                            full_response_content += content
                            yield {"event": "content", "data": {"delta": content}}
                        if chunk.get('done'): break

                try:
                    async for event in do_request(current_tools):
                        yield event
                except Exception as e:
                    if "does not support tools" in str(e).lower() and current_tools:
                        logger.warning(f"Model {model} does not support tools. Retrying without tools...")
                        full_response_content = "" # Reset content for retry
                        async for event in do_request([]):
                            yield event
                    else:
                        raise e
                
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
        
        history = self.db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id).order_by(models.ChatMessage.timestamp.desc()).limit(6).all()
        for msg in reversed(history):
            messages.append({"role": msg.role, "content": msg.content})
            
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _execute_tool(self, name, args):
        """Dispatches tool calls to the appropriate external API."""
        logger.info(f"Executing tool: {name} with args {args}")
        timeout = aiohttp.ClientTimeout(total=60)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if name == "search_web":
                    async with session.get(config.SEARCH_URL, params={"q": args.get("query")}) as r:
                        data = await r.json()
                        results = data.get('results', [])
                        return "\n".join([f"- {r['title']}: {r['body']} ({r['href']})" for r in results[:4]])
                
                elif name == "get_weather":
                    async with session.get(config.WEATHER_URL, params={"location": args.get("location")}) as r:
                        data = await r.json()
                        return f"Weather for {data['location']}: {data['condition']}, Temp: {data['temp']}, Humidity: {data['humidity']}"

                elif name == "read_url":
                    async with session.get(config.SCRAPER_URL, params={"url": args.get("url")}) as r:
                        data = await r.json()
                        return data.get('content', 'No content found.')[:5000]

                elif name == "get_stock_crypto_price":
                    async with session.get(config.FINANCE_URL, params={"symbol": args.get("symbol")}) as r:
                        data = await r.json()
                        return f"Ticker: {data['symbol']}, Price: {data['price']} {data['currency']} (Source: {data['source']})"

                elif name == "track_lego_set":
                    # Note: tracking is a POST in the scraper
                    async with session.post(config.TRACK_URL, params={"url": args.get("url")}) as r:
                        data = await r.json()
                        return data.get('message', 'Update sent to tracker.')

                elif name == "search_images":
                    async with session.get(config.IMAGE_SEARCH_URL, params={"q": args.get("query")}) as r:
                        data = await r.json()
                        return "\n".join([f"- {r['title']}: {r['image']}" for r in data.get('results', [])[:3]])

                elif name == "get_news":
                    async with session.get(config.NEWS_URL, params={"q": args.get("query")}) as r:
                        data = await r.json()
                        return "\n".join([f"- {r['title']}: {r['body']} ({r['url']})" for r in data.get('results', [])[:4]])

                elif name == "read_reddit":
                    async with session.get(config.REDDIT_URL, params={"url": args.get("url")}) as r:
                        data = await r.json()
                        res = f"Title: {data['title']}\nContent: {data['content'][:1000]}\nComments:\n"
                        for c in data.get('comments', []):
                            res += f"- {c['author']}: {c['body'][:150]}\n"
                        return res

                return f"Tool {name} implemented but API returned no data."

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return f"Error connecting to tool service: {e}"

    def _save_history(self, session_id, prompt, response):
        user_msg = models.ChatMessage(session_id=session_id, role="user", content=prompt)
        asst_msg = models.ChatMessage(session_id=session_id, role="assistant", content=response)
        self.db.add(user_msg)
        self.db.add(asst_msg)
        self.db.commit()
