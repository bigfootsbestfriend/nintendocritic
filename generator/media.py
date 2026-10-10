"""Cover art, screenshots and trailers from IGDB for the games in Airtable.

The build looks these up by IGDB ID each time (two or three API calls for ~500 games), so nothing extra lives in
Airtable. Local runs keep a copy in .cache/ to save time. If IGDB can't be reached, the site still builds, just
without images.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))
from common import IGDB  # noqa: E402

CACHE = ROOT / ".cache" / "igdb_media.json"
CACHE_HOURS = 20
IMG = "https://images.igdb.com/igdb/image/upload/{size}/{id}.jpg"
# Best trailer first: launch and release trailers beat teasers and dev diaries.
TRAILER_ORDER = ["launch trailer", "release date trailer", "trailer", "gameplay trailer", "announcement trailer"]


def img(image_id, size="t_cover_big"):
    return IMG.format(size=size, id=image_id)


def trailer_candidates(videos):
    def rank(v):
        name = (v.get("name") or "").lower().strip()
        if name in TRAILER_ORDER:
            return TRAILER_ORDER.index(name)
        return len(TRAILER_ORDER) + (0 if "trailer" in name else 1)
    return [v["video_id"] for v in sorted(videos, key=rank) if v.get("video_id")]


def playable(video_id):
    """True if YouTube allows embedding (oEmbed returns 401/403/404 for blocked, private or removed videos)."""
    q = urllib.parse.urlencode({"url": "https://www.youtube.com/watch?v=" + video_id, "format": "json"})
    try:
        with urllib.request.urlopen("https://www.youtube.com/oembed?" + q, timeout=20):
            return True
    except urllib.error.HTTPError as err:
        return err.code not in (401, 403, 404)
    except OSError:
        return False


def fetch(igdb_ids):
    """{igdb_id: {"cover": image_id|None, "shots": [image_id], "videos": [{name, video_id}]}}"""
    ids = sorted({int(i) for i in igdb_ids if i})
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_HOURS * 3600:
        cached = {int(k): v for k, v in json.loads(CACHE.read_text()).items()}
        if all(i in cached for i in ids):
            return cached
    if not (os.environ.get("IGDB_CLIENT_ID") and os.environ.get("IGDB_CLIENT_SECRET")):
        print("media: no IGDB credentials, building without images")
        return {}
    try:
        igdb = IGDB()
        out = {}
        for i in range(0, len(ids), 500):
            chunk = ",".join(map(str, ids[i:i + 500]))
            rows = igdb.query("games", f"fields cover.image_id,screenshots.image_id,artworks.image_id,videos.name,videos.video_id;"
                                       f" where id = ({chunk}); limit 500;")
            for r in rows:
                out[r["id"]] = {
                    "cover": (r.get("cover") or {}).get("image_id"),
                    "shots": [s["image_id"] for s in r.get("screenshots", []) if s.get("image_id")],
                    "art": [a["image_id"] for a in r.get("artworks", []) if a.get("image_id")],
                    "videos": [{"name": v.get("name"), "video_id": v.get("video_id")} for v in r.get("videos", [])],
                }
    except SystemExit as err:  # common.http raises SystemExit on hard API errors
        print(f"media: IGDB lookup failed ({err}), building without images")
        return {}
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out))
    print(f"media: {sum(1 for m in out.values() if m['cover'])} covers for {len(ids)} games")
    return out
