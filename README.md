# Agent Orchestrator

The AI brain of the Kelor ecosystem. Manages the full lifecycle of a request — LLM inference, tool selection, parallel tool execution, vision analysis, and conversation history — and streams results back to clients via Server-Sent Events.

## Architecture

```
Client (chatbot) ──POST /v1/chat──► Agent Orchestrator
                                         │
                        ┌────────────────┼────────────────┐
                        ▼                ▼                ▼
                    Ollama (LLM)    Tool Execution    Database
                    gemma3:1b       (parallel)        (history +
                    moondream       utility-api       profiles)
                                    webscraper
```

## How the Agent Loop Works

Each request runs a multi-turn loop (max 3 turns):

1. **Assemble context** — inject current date/time, user preferences, and last 6 messages of history into the system prompt
2. **LLM turn** — call Ollama with the full tool schema; the model either responds directly or emits tool calls
3. **Parallel tool execution** — if tools are requested, all calls are dispatched concurrently with `asyncio.gather()`
4. **Continue** — tool results are appended to the message history and the loop continues for the LLM to synthesise a final answer
5. **Stream** — every step emits SSE events the client can render in real time

## SSE Events

| Event | When emitted |
|---|---|
| `status: thinking` | LLM inference started (suppressed in the Discord UI) |
| `status: calling_tool` | One or more tools are executing |
| `status: analysing_image` | Moondream is processing an uploaded image |
| `content` | Incremental LLM text chunk |
| `tool_result` | Result returned from a tool call |
| `final_answer` | Complete final response text |
| `error` | Something went wrong |

## Available Tools

| Tool | Backed by |
|---|---|
| `search_web` | utility-api `/search` |
| `get_weather` | utility-api `/weather` |
| `get_stock_crypto_price` | utility-api `/finance` |
| `get_news` | utility-api `/news` |
| `search_images` | utility-api `/image_search` |
| `read_reddit` | utility-api `/reddit` |
| `summarise_youtube` | utility-api `/youtube` |
| `read_url` | webscraper `/read` |
| `track_lego_set` | webscraper `/track` |

## Vision Support

When a request includes image attachments (JPG, PNG, GIF, WebP), the orchestrator fetches each image, base64-encodes it, and sends it to `moondream` via Ollama before the main LLM turn. The image descriptions are prepended to the user prompt so the primary model can reason about them and use tools based on visual context.

## User Profiles

Each user's preferences are stored and applied to every request:

| Field | Effect |
|---|---|
| `preferred_model` | Which Ollama model to use (default: `gemma3:1b`) |
| `preferred_lang` | Response language injected into system prompt (default: `en` → English) |
| `preferred_temp_unit` | Celsius or Fahrenheit in weather responses |
| `timezone` | Used when answering time-relative questions |

Profiles are managed via `PATCH /v1/users/{user_id}` and `GET /v1/users/{user_id}`.

## API

### `POST /v1/chat`

Initiate an agentic conversation. Returns an SSE stream.

```json
{
  "session_id": "discord-channel-id",
  "user_id": "discord-user-id",
  "prompt": "What is the current price of GOOGL?",
  "attachments": [
    { "url": "https://...", "filename": "chart.png" }
  ]
}
```

### `GET /v1/users/{user_id}`

Fetch a user profile.

### `PATCH /v1/users/{user_id}`

Update a user profile. Accepts any combination of `preferred_model`, `preferred_lang`, `preferred_temp_unit`, `timezone`.

### `GET /health`

Health check. Returns `{"status": "healthy"}`.

## Tech Stack

- **Python 3.14+**
- **FastAPI** + **sse-starlette** — async API with SSE streaming
- **aiohttp** — async HTTP to Ollama and downstream services
- **SQLAlchemy** — conversation history and user profiles (SQLite in dev, PostgreSQL-ready)
- **Ollama** — local LLM inference (default: `gemma3:1b`, vision: `moondream`)

## Setup

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://ollama-service.ai-services.svc.cluster.local:11434/api/generate` | Ollama API endpoint |
| `OLLAMA_MODEL` | `gemma3:1b` | Default chat model |
| `OLLAMA_VISION_MODEL` | `moondream` | Vision model for image analysis |
| `DATABASE_URL` | `sqlite:///./agent_orchestrator.db` | Database connection string |
| `SCRAPER_BASE_URL` | *(k8s default)* | Base URL of the webscraper service |
| `UTILITY_BASE_URL` | *(k8s default)* | Base URL of the utility-api service |

### Running Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

Ensure Ollama is running locally and the `gemma3:1b` and `moondream` models are pulled:

```bash
ollama pull gemma3:1b
ollama pull moondream
```

### Kubernetes

Deployed to the `ai-services` namespace via ArgoCD alongside the Ollama service.

```bash
kubectl apply -k gitops/agent-orchestrator/overlays/dev
```

## Deployment Notes

- Container image built for `linux/arm64` (M1 Mac Mini cluster)
- Pushed to `ghcr.io/wmickeyd/agent-orchestrator` on every push to `main`
- ArgoCD detects the manifest update and redeploys automatically
