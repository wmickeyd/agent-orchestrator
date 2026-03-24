# Agent Orchestrator

The "Brain" of the ecosystem. This service decouples complex AI orchestration, tool execution, and state management from the user interface (e.g., the Discord Thin Client).

## Overview

The Agent Orchestrator manages the lifecycle of an AI request. Instead of a simple prompt-response, it executes a **multi-turn agentic loop**:
1.  **Analyze**: Understand the user's intent.
2.  **Act**: Decide if a tool (search, weather, etc.) is needed.
3.  **Observe**: Process the tool's output.
4.  **Synthesize**: Provide a final answer based on real-time data.

## Features

- **SSE Streaming**: Provides real-time updates to the client via Server-Sent Events (`status`, `content`, `tool_result`, `final_answer`).
- **Tool Orchestration**: Deeply integrated with `utility-api` and `webscraper`.
- **Session Memory**: Automatically manages conversation history in a persistent database.
- **User Profiles**: Respects user-specific preferences like preferred LLM models and units.
- **Async Execution**: Built on FastAPI and `aiohttp` for high-concurrency performance.

## Tech Stack

- **Framework**: FastAPI
- **Inference**: Ollama (via REST)
- **Database**: SQLAlchemy (SQLite for dev, Postgres-ready)
- **Streaming**: `sse-starlette`
- **Communication**: `aiohttp`

## API Contract

### `POST /v1/chat`
The primary endpoint for initiating an agentic conversation.

**Request:**
```json
{
  "session_id": "unique-channel-id",
  "user_id": "unique-user-id",
  "prompt": "What is the current price of Bitcoin?",
  "attachments": []
}
```

**Response (SSE Stream):**
- `event: status`: Updates on the agent's state (e.g., `thinking`, `calling_tool`).
- `event: content`: Incremental text chunks of the response.
- `event: tool_result`: Data returned from a tool execution.
- `event: final_answer`: The complete final response.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    Create a `.env` file with the following:
    - `OLLAMA_URL`: URL to your Ollama service (default: `http://ollama-service.ai-services.svc.cluster.local:11434/api/generate`)
    - `DATABASE_URL`: Your database connection string.
    - `SCRAPER_BASE_URL`: URL to the `webscraper` service.
    - `UTILITY_BASE_URL`: URL to the `utility-api` service.

3.  **Run Service**:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
    ```

## Kubernetes Deployment

The service is designed to run in the `ai-services` namespace, alongside Ollama.

```bash
kubectl apply -k deploy/overlays/dev
```
