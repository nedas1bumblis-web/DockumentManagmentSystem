"""Central settings. Everything that may change lives here or in .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- AI models (override in .env; model names get retired, never hard-code them elsewhere) ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))   # 768 / 1536 / 3072 are the sizes Google recommends
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# True -> no network calls to Gemini (unit tests, Locust load test, demos without a key)
USE_MOCK_AI = os.getenv("USE_MOCK_AI", "0") == "1"

# --- Chunking ---
CHUNK_SIZE = 1000      # characters
CHUNK_OVERLAP = 150    # characters
TOP_K = 5              # chunks sent to the LLM per question

# --- Uploads ---
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "storage/uploads")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_DOCUMENTS_PER_USER = 1000    # QA A3
