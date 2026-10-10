"""Shared helpers for the Nintendo Critic collectors: env loading, HTTP, IGDB and Airtable clients.

Standard library only, so the GitHub Action needs no pip install.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_ID = "appSsH1VGhRnPpTc3"
GAMES_TABLE = "tblDjV6sGOFOgFEfc"
COMPAT_TABLE = "tblW3npY6xwG5f6EW"
CHANGELOG_TABLE = "tbl1JcXYHhftssbjS"
REVIEWS_TABLE = "tblGYKZJDlxJCvXfW"

IGDB_SWITCH2 = 508


def load_env():
    """Read ../.env for local runs; in GitHub Actions the secrets are already in the environment."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    missing = [k for k in ("IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET", "AIRTABLE_TOKEN") if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing secrets: " + ", ".join(missing))


def http(method, url, headers=None, data=None, retries=4):
    body = None
    if data is not None:
        body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            # 429 = rate limited (IGDB 4/s, Airtable 5/s); back off and retry
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"{method} {url} failed: {e.code} {e.read().decode()[:500]}")
    raise SystemExit(f"{method} {url} failed after {retries} retries")


def norm(name):
    """Loose title key for matching rows: drop bracketed notes and everything but letters/digits."""
    name = re.sub(r"\([^)]*\)", "", name or "")
    return re.sub(r"[^a-z0-9]", "", name.lower())


class IGDB:
    def __init__(self):
        q = urllib.parse.urlencode({
            "client_id": os.environ["IGDB_CLIENT_ID"],
            "client_secret": os.environ["IGDB_CLIENT_SECRET"],
            "grant_type": "client_credentials",
        })
        tok = http("POST", "https://id.twitch.tv/oauth2/token?" + q)["access_token"]
        self.headers = {"Client-ID": os.environ["IGDB_CLIENT_ID"], "Authorization": "Bearer " + tok}

    def query(self, endpoint, body):
        time.sleep(0.3)
        return http("POST", "https://api.igdb.com/v4/" + endpoint, self.headers, body)


class Airtable:
    def __init__(self, dry_run=False):
        self.headers = {"Authorization": "Bearer " + os.environ["AIRTABLE_TOKEN"], "Content-Type": "application/json"}
        self.dry_run = dry_run

    def _url(self, table):
        return f"https://api.airtable.com/v0/{BASE_ID}/{table}"

    def all(self, table):
        rows, offset = [], None
        while True:
            url = self._url(table) + ("?offset=" + offset if offset else "")
            page = http("GET", url, self.headers)
            rows += page["records"]
            offset = page.get("offset")
            if not offset:
                return rows
            time.sleep(0.25)

    def _batched(self, method, table, records):
        out = []
        for i in range(0, len(records), 10):  # Airtable takes 10 records per write
            chunk = records[i:i + 10]
            if self.dry_run:
                out += chunk
                continue
            out += http(method, self._url(table), self.headers, {"records": chunk, "typecast": True})["records"]
            time.sleep(0.25)
        return out

    def create(self, table, fields_list):
        return self._batched("POST", table, [{"fields": f} for f in fields_list])

    def update(self, table, updates):
        """updates: list of (record_id, fields)."""
        return self._batched("PATCH", table, [{"id": rid, "fields": f} for rid, f in updates])
