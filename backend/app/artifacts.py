"""Content-addressed artifact storage on the local filesystem (pluggable later)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from sqlalchemy.orm import Session
from .config import ARTIFACT_DIR
from .models import Artifact


def store(db: Session, project_id: str, kind: str, filename: str, content: bytes,
          content_type: str = "application/octet-stream", label: str = "") -> Artifact:
    digest = hashlib.sha256(content).hexdigest()
    folder = ARTIFACT_DIR / project_id / digest[:2]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / digest
    if not path.exists():
        path.write_bytes(content)
    art = Artifact(project_id=project_id, kind=kind, filename=filename, content_type=content_type,
                   size=len(content), sha256=digest, storage_path=str(path.relative_to(ARTIFACT_DIR)), label=label)
    db.add(art)
    db.flush()
    return art


def read(art: Artifact) -> bytes:
    return (ARTIFACT_DIR / art.storage_path).read_bytes()


def verify(art: Artifact) -> bool:
    return hashlib.sha256(read(art)).hexdigest() == art.sha256
