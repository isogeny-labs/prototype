"""Settings: where data lives and which ports are used. Everything binds to 127.0.0.1."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "demo"
DEMO_CBOM = DEMO_DIR / "acme-pay-cbom.json"
EXPECTED_JSON = DEMO_DIR / "expected.json"  # answer key: read-only, never written by the app
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

BIND_HOST = "127.0.0.1"
DEMO_HOSTNAME = "localhost"
DEMO_CBOM_PORT = 8443  # the port written in demo/acme-pay-cbom.json
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_CLAIMS_PER_FILE = 500

COMPONENTS_DIR = DEMO_DIR / "components"
VECTORS_DIR = DEMO_DIR / "vectors"
# Container base images, pinned by digest. Only `python -m app.prepare` may pull or build; the app never does.
PYTHON_BASE_IMAGE = "python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7"
OPENSSL_IMAGE = "alpine/openssl@sha256:6821afa2476e11be343f29275f2ca24291720ff0a7148bd131fd8e314ff26d9e"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    demo_tls_port: int
    max_jobs: int = 4               # tests running at once (EVIDENCE_LAB_MAX_JOBS, 1..16)
    force_mode: str | None = None   # "demo" | "isolated" | None = decide from what is available (EVIDENCE_LAB_MODE)
    # Speed test: many short rounds, so the versions take turns every fraction of a second and a busy moment on
    # the computer hits them alike. rounds * repeats = pairs (200).
    speed_rounds: int = 40          # bench rounds (EVIDENCE_LAB_SPEED_ROUNDS, 2..50)
    speed_repeats: int = 5          # sign+verify pairs per round

    @property
    def db_path(self) -> Path:
        return self.data_dir / "evidence-lab.sqlite3"

    @property
    def demo_address(self) -> str:
        return f"{DEMO_HOSTNAME}:{self.demo_tls_port}"


def load_settings(data_dir: str | os.PathLike | None = None, demo_tls_port: int | None = None) -> Settings:
    if data_dir is None:
        data_dir = os.environ.get("EVIDENCE_LAB_DATA_DIR") or (REPO_ROOT / "data")
    if demo_tls_port is None:
        raw = os.environ.get("EVIDENCE_LAB_DEMO_TLS_PORT", "8443")
        try:
            demo_tls_port = int(raw)
        except ValueError:
            raise SystemExit("EVIDENCE_LAB_DEMO_TLS_PORT must be a number between 1 and 65535")
    if not 1 <= demo_tls_port <= 65535:
        raise SystemExit("EVIDENCE_LAB_DEMO_TLS_PORT must be a number between 1 and 65535")
    force_mode = os.environ.get("EVIDENCE_LAB_MODE", "").strip().lower() or None
    if force_mode == "auto":
        force_mode = None
    if force_mode not in (None, "demo", "isolated"):
        raise SystemExit("EVIDENCE_LAB_MODE must be demo, isolated or auto")
    return Settings(data_dir=Path(data_dir).resolve(), demo_tls_port=demo_tls_port,
                    max_jobs=_env_int("EVIDENCE_LAB_MAX_JOBS", 4, 1, 16), force_mode=force_mode,
                    speed_rounds=_env_int("EVIDENCE_LAB_SPEED_ROUNDS", 40, 2, 50))


def _env_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        value = low - 1
    if not low <= value <= high:
        raise SystemExit(f"{name} must be a number between {low} and {high}")
    return value
