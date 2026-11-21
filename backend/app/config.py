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
    # Phase 6, Otto's research loop: "Look for new advisories" reads the public source (OSV) unless this names a folder
    # of recorded answers on this computer (tests, the walks, a demo with no internet). Then nothing is sent anywhere.
    advisory_source_dir: Path | None = None    # EVIDENCE_LAB_ADVISORY_SOURCE
    # Hosting (app/infra/): where the database, the cache and stored files live, and who may log in. None of these
    # is needed for the demo on one computer: unset, the app keeps its SQLite file and folders in the data folder, a
    # cache in memory, and the password login, exactly as before.
    database_url: str | None = None            # EVIDENCE_LAB_DATABASE_URL: sqlite:///... or postgresql://...
    redis_url: str | None = None               # EVIDENCE_LAB_REDIS_URL: redis://host:6379/0
    storage_url: str | None = None             # EVIDENCE_LAB_STORAGE_URL: s3://bucket/prefix, gs://bucket/prefix or a folder
    public_url: str | None = None              # EVIDENCE_LAB_PUBLIC_URL: https://lab.example.com (the address people open)
    allowed_hosts: tuple[str, ...] = ()        # EVIDENCE_LAB_ALLOWED_HOSTS: extra host names the app answers, comma-separated
    password_login: bool = True                # EVIDENCE_LAB_PASSWORD_LOGIN (default: off when the GitHub login is set up)
    github: GitHubSettings | None = None       # EVIDENCE_LAB_GITHUB_*: the GitHub App used to log in

    @property
    def database(self) -> str:
        """The SQLAlchemy URL of the database: the one named, or the SQLite file in the data folder."""
        return self.database_url or f"sqlite:///{self.db_path}"

    @property
    def login_methods(self) -> frozenset[str]:
        return frozenset({"password"} if self.password_login else set()) | (
            frozenset({"github"}) if self.github is not None else frozenset())

    @property
    def secure_cookies(self) -> bool:
        return bool(self.public_url and self.public_url.startswith("https://"))

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
        """Packs built on this computer by the research command (signed with this computer's own key)."""
        return self.data_dir / "otto-updates"

    @property
    def otto_recorded(self) -> Path:
        return self.otto_recorded_dir or OTTO_RECORDED_DIR


@dataclass(frozen=True)
class GitHubSettings:
    """A GitHub App that people log in with (its "user-to-server" login). Only the client id and secret are needed;
    the App's private key is not, since this app only asks who the person is (and, if `allowed_orgs` is set, which
    organizations they belong to)."""
    client_id: str
    client_secret: str
    app_slug: str | None = None                 # EVIDENCE_LAB_GITHUB_APP_SLUG: for the "install the app" link
    allowed_users: frozenset[str] = frozenset()  # EVIDENCE_LAB_GITHUB_ALLOWED_USERS: GitHub logins or numeric ids
    allowed_orgs: frozenset[str] = frozenset()   # EVIDENCE_LAB_GITHUB_ALLOWED_ORGS: organization logins, comma-separated
    allow_anyone: bool = False                   # EVIDENCE_LAB_GITHUB_ALLOW_ANYONE: on lets every GitHub account in
    web_url: str = "https://github.com"         # EVIDENCE_LAB_GITHUB_WEB_URL (GitHub Enterprise, or tests)
    api_url: str = "https://api.github.com"     # EVIDENCE_LAB_GITHUB_API_URL

    @property
    def open_to_anyone(self) -> bool:
        return self.allow_anyone


def _csv(raw: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (raw or "").split(",") if part.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise SystemExit(f"{name} must be on or off")


def _database_url() -> str | None:
    """EVIDENCE_LAB_DATABASE_URL, with EVIDENCE_LAB_DATABASE_PASSWORD put in when given (a secret store can then hand
    over the password alone, and the URL holds none)."""
    url = (os.environ.get("EVIDENCE_LAB_DATABASE_URL") or "").strip() or None
    password = os.environ.get("EVIDENCE_LAB_DATABASE_PASSWORD")
    if url and password:
        from sqlalchemy.engine import make_url
        url = make_url(url).set(password=password).render_as_string(hide_password=False)
    return url


def load_github_settings() -> GitHubSettings | None:
    client_id = (os.environ.get("EVIDENCE_LAB_GITHUB_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("EVIDENCE_LAB_GITHUB_CLIENT_SECRET") or "").strip()
    if not client_id and not client_secret:
        return None
    if not client_id or not client_secret:
        raise SystemExit("EVIDENCE_LAB_GITHUB_CLIENT_ID and EVIDENCE_LAB_GITHUB_CLIENT_SECRET must be set together")
    users = frozenset(u.lower() for u in _csv(os.environ.get("EVIDENCE_LAB_GITHUB_ALLOWED_USERS")))
    orgs = frozenset(o.lower() for o in _csv(os.environ.get("EVIDENCE_LAB_GITHUB_ALLOWED_ORGS")))
    anyone = _env_bool("EVIDENCE_LAB_GITHUB_ALLOW_ANYONE", False)
    if not users and not orgs and not anyone:
        # Every login sees and can change the same assessments: who may log in is never left open by accident.
        raise SystemExit("The GitHub login needs EVIDENCE_LAB_GITHUB_ALLOWED_USERS or EVIDENCE_LAB_GITHUB_ALLOWED_ORGS "
                         "(or EVIDENCE_LAB_GITHUB_ALLOW_ANYONE=on to let every GitHub account in)")
    return GitHubSettings(
        client_id=client_id, client_secret=client_secret,
        app_slug=(os.environ.get("EVIDENCE_LAB_GITHUB_APP_SLUG") or "").strip() or None,
        allowed_users=users, allowed_orgs=orgs, allow_anyone=anyone,
        web_url=(os.environ.get("EVIDENCE_LAB_GITHUB_WEB_URL") or "https://github.com").rstrip("/"),
        api_url=(os.environ.get("EVIDENCE_LAB_GITHUB_API_URL") or "https://api.github.com").rstrip("/"))


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
    advisory_source = os.environ.get("EVIDENCE_LAB_ADVISORY_SOURCE")
    github = load_github_settings()
    settings = Settings(data_dir=Path(data_dir).resolve(), demo_tls_port=demo_tls_port,
                    max_jobs=_env_int("EVIDENCE_LAB_MAX_JOBS", 4, 1, 16), force_mode=force_mode,
                    speed_rounds=_env_int("EVIDENCE_LAB_SPEED_ROUNDS", 40, 2, 50),
                    otto_updates_dir=Path(updates).resolve() if updates else None,
                    otto_recorded_dir=Path(recorded).resolve() if recorded else None,
                    advisory_source_dir=Path(advisory_source).resolve() if advisory_source else None,
                    database_url=_database_url(),
                    redis_url=(os.environ.get("EVIDENCE_LAB_REDIS_URL") or "").strip() or None,
                    storage_url=(os.environ.get("EVIDENCE_LAB_STORAGE_URL") or "").strip() or None,
                    public_url=(os.environ.get("EVIDENCE_LAB_PUBLIC_URL") or "").strip().rstrip("/") or None,
                    allowed_hosts=_csv(os.environ.get("EVIDENCE_LAB_ALLOWED_HOSTS")),
                    # With the GitHub login set up, the password login is off unless asked for: on a hosted copy the
                    # first visitor would otherwise choose the password.
                    password_login=_env_bool("EVIDENCE_LAB_PASSWORD_LOGIN", github is None),
                    github=github)
    if not settings.password_login and settings.github is None:
        raise SystemExit("EVIDENCE_LAB_PASSWORD_LOGIN=off needs the GitHub login (EVIDENCE_LAB_GITHUB_CLIENT_ID and _SECRET)")
    return settings


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
