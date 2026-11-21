"""`python -m app` starts Evidence Lab on this computer only (http://127.0.0.1:8000).

Hosting (a container): EVIDENCE_LAB_BIND_HOST=0.0.0.0 and EVIDENCE_LAB_PORT choose where it listens.
"""
import os

import uvicorn

from app.main import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host=os.environ.get("EVIDENCE_LAB_BIND_HOST") or "127.0.0.1",
                port=int(os.environ.get("EVIDENCE_LAB_PORT") or 8000), log_level="info",
                proxy_headers=True, forwarded_allow_ips=os.environ.get("EVIDENCE_LAB_FORWARDED_ALLOW_IPS") or "127.0.0.1")
