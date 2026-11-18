"""Settings: where data lives and which ports are used. Everything binds to 127.0.0.1."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "demo"
DEMO_CBOM = DEMO_DIR / "acme-pay-cbom.json"
EXPECTED_JSON = DEMO_DIR / "expected.json"  # answer key: read-only, never written by the app
EXPECTED_MIGRATION_JSON = DEMO_DIR / "expected-migration.json"  # the migration demo's answer key: read-only too
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
OTTO_PACKS_DIR = REPO_ROOT / "research" / "packs"        # phase 5c: the signed test packs shipped with the app
OTTO_RECORDED_DIR = REPO_ROOT / "research" / "recorded"  # phase 5c: Claude's answers recorded during the build

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
# Phase 4b: the real nginx of the lab (nginx 1.31.8 on OpenSSL 3.5.9), pinned by digest. Pulled only by app.prepare.
NGINX_IMAGE = "nginx@sha256:fed7e14be83cbd2661a75cdc5b872d936cf155d46c327084d30b8df19ae88d72"


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
    # The three local test servers of the multi-target demo file (phase 3a-fixes). Started only when that file is imported.
    extra_ports: tuple[int, int, int] = (8444, 8445, 8446)
    # The five local test servers of the migration demo file (phase 4a). Started only when that file is imported.
    migration_ports: tuple[int, int, int, int, int] = (8451, 8452, 8453, 8454, 8455)
    # The lab nginx of demo/lab-nginx.csv (phase 4b): real nginx in isolated mode, started only when that file is imported.
    lab_nginx_port: int = 8461
    # Phase 5c: the updates folder "Check for updates" looks in (on this computer, never the internet), and the
    # folder of Claude's recorded answers. None means the ones shipped in the repository (research/packs, research/recorded).
    otto_updates_dir: Path | None = None       # EVIDENCE_LAB_OTTO_UPDATES
    otto_recorded_dir: Path | None = None      # EVIDENCE_LAB_OTTO_RECORDED

    @property
    def db_path(self) -> Path:
        return self.data_dir / "evidence-lab.sqlite3"

    @property
    def demo_address(self) -> str:
        return f"{DEMO_HOSTNAME}:{self.demo_tls_port}"

    @property
    def otto_updates(self) -> Path:
        return self.otto_updates_dir or OTTO_PACKS_DIR

    @property
    def otto_local_updates(self) -> Path:
        """Packs built on this computer by the live research command (signed with this computer's own key)."""
        return self.data_dir / "otto-updates"

    @property
    def otto_recorded(self) -> Path:
        return self.otto_recorded_dir or OTTO_RECORDED_DIR


def load_settings(data_dir: str | os.PathLike | None = None, demo_tls_port: int | None = None) -> Settings:
    if data_dir is None:
        data_dir = os.environ.get("EVIDENCE_LAB_DATA_DIR") or (REPO_ROOT / "data")
    if demo_tls_port is None:
        raw = os.environ.get("EVIDENCE_LAB_DEMO_TLS_PORT", "8443")
        try:
            demo_tls_port = int(raw)
        except ValueError:
            raise SystemExit("EVIDENCE_LAB_DEMO_TLS_PORT must be a number between 1 and 65535")  # noqa: B904
    if not 1 <= demo_tls_port <= 65535:
        raise SystemExit("EVIDENCE_LAB_DEMO_TLS_PORT must be a number between 1 and 65535")
    force_mode = os.environ.get("EVIDENCE_LAB_MODE", "").strip().lower() or None
    if force_mode == "auto":
        force_mode = None
    if force_mode not in (None, "demo", "isolated"):
        raise SystemExit("EVIDENCE_LAB_MODE must be demo, isolated or auto")
    updates, recorded = os.environ.get("EVIDENCE_LAB_OTTO_UPDATES"), os.environ.get("EVIDENCE_LAB_OTTO_RECORDED")
    return Settings(data_dir=Path(data_dir).resolve(), demo_tls_port=demo_tls_port,
                    max_jobs=_env_int("EVIDENCE_LAB_MAX_JOBS", 4, 1, 16), force_mode=force_mode,
                    speed_rounds=_env_int("EVIDENCE_LAB_SPEED_ROUNDS", 40, 2, 50),
                    otto_updates_dir=Path(updates).resolve() if updates else None,
                    otto_recorded_dir=Path(recorded).resolve() if recorded else None)


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
