import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agent_orchestrator.db")

# Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama-service.ai-services.svc.cluster.local:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream")

# Downstream APIs
SCRAPER_BASE_URL = os.getenv("SCRAPER_BASE_URL", "http://dev-webscraper.webscraper-dev.svc.cluster.local:8000")
UTILITY_BASE_URL = os.getenv("UTILITY_BASE_URL", "http://dev-utility-api.utility-dev.svc.cluster.local:8001")

SCRAPER_URL = f"{SCRAPER_BASE_URL}/read"
TRACK_URL = f"{SCRAPER_BASE_URL}/track"
FINANCE_URL = f"{UTILITY_BASE_URL}/finance"
SEARCH_URL = f"{UTILITY_BASE_URL}/search"
IMAGE_SEARCH_URL = f"{UTILITY_BASE_URL}/image_search"
WEATHER_URL = f"{UTILITY_BASE_URL}/weather"
NEWS_URL = f"{UTILITY_BASE_URL}/news"
REDDIT_URL = f"{UTILITY_BASE_URL}/reddit"
YOUTUBE_URL = f"{UTILITY_BASE_URL}/youtube"
