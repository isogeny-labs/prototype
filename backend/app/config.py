"""Server configuration. Secrets stay server-side; nothing here is logged verbatim."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("IEL_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("IEL_DATABASE_URL", f"sqlite:///{DATA_DIR / 'iel.sqlite3'}")
ARTIFACT_DIR = Path(os.environ.get("IEL_ARTIFACT_DIR", DATA_DIR / "artifacts"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
FIXTURE_DIR = ROOT / "backend" / "fixtures"
FRONTEND_DIR = ROOT / "frontend"
SEED_DIR = ROOT / "seeds"

# Optional AI provider adapter. Absent key => rule-based extraction (labelled in UI).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AI_MODEL = os.environ.get("IEL_AI_MODEL", "claude-sonnet-5-5")

# Runner limits (process-isolated local fixture runner)
RUNNER_TIMEOUT_SECONDS = int(os.environ.get("IEL_RUNNER_TIMEOUT", "300"))
RUNNER_MEMORY_LIMIT_MB = int(os.environ.get("IEL_RUNNER_MEMORY_MB", "1024"))
RUNNER_CPU_SECONDS = int(os.environ.get("IEL_RUNNER_CPU_SECONDS", "240"))

# Background worker: in-process thread by default; set IEL_WORKER=external to run `python -m app.worker`.
WORKER_MODE = os.environ.get("IEL_WORKER", "thread")
SESSION_TTL_HOURS = int(os.environ.get("IEL_SESSION_TTL_HOURS", "24"))
