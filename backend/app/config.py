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
MODE = "demo"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    demo_tls_port: int

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
    return Settings(data_dir=Path(data_dir).resolve(), demo_tls_port=demo_tls_port)
