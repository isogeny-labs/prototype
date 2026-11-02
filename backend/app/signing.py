"""Platform signing identity and trust-policy helpers.

The platform's Ed25519 key lives at IEL_PLATFORM_KEY_PATH (default data/keys/platform_ed25519.pem, mode 0600), outside
artifacts and source control. Its public key is registered as a platform-wide trusted key on first start.
Rotation: generate a new key file, start the platform, then revoke the old TrustedKey record (docs/ATTESTATION.md).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from iel_tools import attest  # noqa: E402

from .config import DATA_DIR  # noqa: E402

KEY_PATH = Path(os.environ.get("IEL_PLATFORM_KEY_PATH", DATA_DIR / "keys" / "platform_ed25519.pem"))
_cache = {}


def platform_private_key():
    if "key" in _cache:
        return _cache["key"]
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        key = attest.private_key_from_pem(KEY_PATH.read_bytes())
    else:
        key = attest.generate_private_key()
        KEY_PATH.write_bytes(attest.private_key_to_pem(key))
        os.chmod(KEY_PATH, 0o600)
    _cache["key"] = key
    return key


def platform_public_pem() -> str:
    return attest.public_key_to_pem(platform_private_key().public_key())


def platform_key_id() -> str:
    return attest.key_id(platform_private_key().public_key())


def trusted_keys_for(db, project_id: str | None, purpose: str) -> dict:
    """keyid -> (name, public key) for ACTIVE keys: project-specific plus platform-wide (project_id NULL)."""
    from sqlalchemy import select
    from .models import TrustedKey
    q = select(TrustedKey).where(TrustedKey.status == "active", TrustedKey.purpose == purpose)
    out = {}
    for k in db.scalars(q).all():
        if k.project_id in (None, project_id):
            try:
                out[k.key_id] = (k.name, attest.public_key_from_pem(k.public_key_pem))
            except Exception:  # noqa: BLE001
                continue
    return out


def ensure_platform_key_registered(db, actor_id=None):
    from sqlalchemy import select
    from .models import TrustedKey
    kid = platform_key_id()
    if not db.scalar(select(TrustedKey).where(TrustedKey.key_id == kid)):
        db.add(TrustedKey(project_id=None, key_id=kid, name="platform signing key", public_key_pem=platform_public_pem(),
                          purpose="platform", status="active", note="Auto-registered from IEL_PLATFORM_KEY_PATH", added_by=actor_id))
        db.commit()
