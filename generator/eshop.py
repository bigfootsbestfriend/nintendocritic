"""Live US Nintendo eShop prices (and sales) for the build: Switch 2 Editions, upgrade packs and Switch 2 games.

Uses the public search index that nintendo.com's own store search queries (Algolia, with the read-only key the
site ships). It isn't an official API, so every failure is soft: the build falls back to the last deployed
static/prices.json, and each price carries the date it was checked. A handful of batched requests per build.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "eshop.json"
CACHE_HOURS = 20
URL = "https://u3b6gr4ua3-dsn.algolia.net/1/indexes/*/queries"
HEADERS = {"x-algolia-application-id": "U3B6GR4UA3", "x-algolia-api-key": "a29c6927638bfd8cee23993e51e721c9",
           "content-type": "application/json", "user-agent": "NintendoCritic/1.0 (nightly price check; hello@nintendocritic.com)"}
STORE = "https://www.nintendo.com"
LIVE = "https://nintendocritic.com/static/prices.json"


def key(s):
    s = re.sub(r"[™®©]", "", s or "").lower().replace("&", "and")
    s = re.sub(r"\s*[–-]\s*nintendo switch 2 edition.*$", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _query(queries):
    out = []
    for i in range(0, len(queries), 40):
        body = json.dumps({"requests": [{"indexName": "store_game_en_us", "params": f"query={urllib.request.quote(q)}&hitsPerPage=12"}
                                        for q in queries[i:i + 40]]}).encode()
        req = urllib.request.Request(URL, body, HEADERS)
        out += json.loads(urllib.request.urlopen(req, timeout=30).read())["results"]
        time.sleep(1)
    return out


def _offer(h):
    p = h.get("price") or {}
    if not p.get("regPrice"):
        return None
    o = {"price": p["regPrice"], "url": STORE + h.get("url", ""), "title": re.sub(r"[™®]", "", h.get("title", ""))}
    if p.get("discounted") and p.get("salePrice"):
        o["sale"] = p["salePrice"]
        o["off"] = p.get("percentOff") or round(100 * (1 - p["salePrice"] / p["regPrice"]))
    return o


def _pick(hits, name, want):
    """want: 'edition' (Switch 2 Edition of a Switch 1 game), 'pack' (its upgrade pack) or 'game' (a Switch 2 game)."""
    k = key(name)
    best = None
    for h in hits:
        t = h.get("title", "")
        if h.get("platform") != "Nintendo Switch 2" or not key(t).startswith(k):
            continue
        pack = "upgrade pack" in t.lower()
        if want == "pack" and not pack or want != "pack" and pack:
            continue
        if want == "edition" and "switch 2 edition" not in t.lower().replace("™", ""):
            continue
        if any(x in t.lower() for x in ("bundle", "+ amiibo", "season pass", "dlc", "expansion pass")):
            continue
        # The shortest matching title is the base product, not a bundle or deluxe version.
        if best is None or len(t) < len(best.get("title", "")):
            best = h
    return _offer(best) if best else None


def _fallback():
    try:
        return json.loads(urllib.request.urlopen(LIVE, timeout=20).read())
    except Exception:
        return {"checked": None, "upgrades": {}, "games": {}}


def fetch(upgrade_names, game_names):
    """Returns {"checked": date, "upgrades": {name: {"edition": offer, "pack": offer}}, "games": {name: offer}}."""
    up, gm = sorted(set(upgrade_names)), sorted(set(game_names))
    names = up + ["|"] + gm
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_HOURS * 3600:
        cached = json.loads(CACHE.read_text())
        if cached.pop("names", None) == names:
            return cached
    try:
        res = _query([f"{n} Nintendo Switch 2 Edition" for n in up] + [f"{n}" for n in gm])
        out = {"checked": time.strftime("%Y-%m-%d"), "upgrades": {}, "games": {}}
        for n, r in zip(up, res[:len(up)]):
            o = {"edition": _pick(r["hits"], n, "edition"), "pack": _pick(r["hits"], n, "pack")}
            if o["edition"] or o["pack"]:
                out["upgrades"][n] = o
        for n, r in zip(gm, res[len(up):]):
            o = _pick(r["hits"], n, "game")
            if o:
                out["games"][n] = o
        if not out["upgrades"] and not out["games"]:
            raise RuntimeError("no prices matched")
    except Exception as ex:
        print(f"eShop prices unavailable ({str(ex)[:80]}); using the last deployed copy")
        return _fallback()
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(dict(out, names=names)))
    return out
