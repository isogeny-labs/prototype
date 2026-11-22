"""A stand-in for GitHub's login, for trying the GitHub login on one computer without a real GitHub App.

    .venv/bin/python tools/fake_github.py --port 8099 --login octocat [--org isogeny-labs]

then start the app with
    EVIDENCE_LAB_GITHUB_CLIENT_ID=Iv1.fake EVIDENCE_LAB_GITHUB_CLIENT_SECRET=fake-secret \
    EVIDENCE_LAB_GITHUB_WEB_URL=http://127.0.0.1:8099 EVIDENCE_LAB_GITHUB_API_URL=http://127.0.0.1:8099/api \
    EVIDENCE_LAB_GITHUB_ALLOWED_USERS=octocat

"Log in with GitHub" then goes to this server, which sends the browser straight back with a code, as GitHub does
after a person clicks Authorize. Test data only; it listens on 127.0.0.1 unless --host says otherwise.
"""

from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

CLIENT_ID, CLIENT_SECRET = "Iv1.fake", "fake-secret"


def handler(login: str, orgs: list[str]):
    codes: dict[str, str] = {}
    tokens: set[str] = set()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, body) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/login/oauth/authorize":
                if query.get("client_id") != [CLIENT_ID]:
                    return self._json(400, {"error": "unknown client"})
                code = secrets.token_urlsafe(16)
                codes[code] = query["redirect_uri"][0]
                back = query["redirect_uri"][0] + "?" + urlencode({"code": code, "state": query["state"][0]})
                self.send_response(302)
                self.send_header("Location", back)
                self.end_headers()
                return None
            if self.headers.get("Authorization", "").removeprefix("Bearer ") not in tokens:
                return self._json(401, {"message": "Bad credentials"})
            if url.path == "/api/user":
                return self._json(200, {"id": 424242, "login": login, "name": f"{login} (fake)", "avatar_url": None})
            if url.path.startswith("/api/user/memberships/orgs/"):
                org = url.path.rsplit("/", 1)[1]
                if org not in orgs:
                    return self._json(404, {"message": "Not Found"})
                return self._json(200, {"state": "active", "role": "member", "organization": {"login": org}})
            return self._json(404, {"message": "Not Found"})

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/login/oauth/access_token":
                return self._json(404, {"message": "Not Found"})
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
            code = (form.get("code") or [""])[0]
            if (
                form.get("client_secret") != [CLIENT_SECRET]
                or codes.pop(code, None) != (form.get("redirect_uri") or [""])[0]
            ):
                return self._json(200, {"error": "bad_verification_code"})
            token = "ghu_fake_" + secrets.token_urlsafe(16)
            tokens.add(token)
            return self._json(200, {"access_token": token, "token_type": "bearer"})

        def log_message(self, fmt, *args):
            print("fake-github:", fmt % args)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="where to listen (0.0.0.0 inside a container)")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--login", default="octocat")
    parser.add_argument("--org", action="append", default=[])
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler(args.login, args.org))
    print(f"fake GitHub on http://{args.host}:{args.port} (login {args.login})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
