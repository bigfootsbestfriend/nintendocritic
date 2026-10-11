"""Email the people waiting for a sale (game pages and the upgrade calculator) when the eShop starts one.

The deploy workflow saves the live site's static/prices.json before deploying, then runs this with the new build's
copy. A sale counts when an item had no sale price before (or a higher one). Each sale is sent once: the
newsletter Worker remembers (item, change) pairs.

    python3 collector/sale_alerts.py old-prices.json public/static/prices.json
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

API = "https://newsletter.crossplayguide.workers.dev/notify"
SITE = "https://nintendocritic.com"
MAX_SALES = 40   # a huge eShop sale is possible, but more than this at once is more likely bad data


def slugify(name):
    """Same as generator/build.py, so alert items match the calculator's."""
    name = re.sub(r"\s*[–-]\s*Nintendo Switch 2 Edition$", " Switch 2 Edition", name)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def new_sale(old, new):
    if not new or not new.get("sale"):
        return False
    return not (old and old.get("sale")) or new["sale"] < old["sale"] - 0.01


def money(o):
    return f'${o["sale"]:.2f} ({round(o["off"])}% off, usually ${o["price"]:.2f})'


def main():
    old_path, new_path = Path(sys.argv[1]), Path(sys.argv[2])
    if not old_path.exists() or not old_path.stat().st_size:
        print("No earlier prices.json (first run?): nothing to compare.")
        return
    old, new = json.loads(old_path.read_text()), json.loads(new_path.read_text())
    if not new.get("checked") or new.get("checked") == old.get("checked") and new == old:
        print("Prices unchanged (or the eShop wasn't reachable): nothing to send.")
        return
    sends = []
    for name, o in new.get("games", {}).items():
        slug = new.get("slugs", {}).get(name)
        if slug and new_sale(old.get("games", {}).get(name), o):
            sends.append((f"sale-{slug}", f"{name} is on sale: {money(o)}",
                          f"{name} is on sale on the Nintendo eShop (US): {money(o)}. Sales end without warning.",
                          f"{SITE}/games/{slug}/", f'{o["sale"]:.2f}'))
    for name, live in new.get("upgrades", {}).items():
        was = old.get("upgrades", {}).get(name) or {}
        parts = [f"the {what} is {money(live[k])}" for k, what in (("edition", "Switch 2 Edition"), ("pack", "upgrade pack"))
                 if new_sale(was.get(k), live.get(k))]
        if parts:
            change = "-".join(f'{live[k]["sale"]:.2f}' if live.get(k) and live[k].get("sale") else "x" for k in ("edition", "pack"))
            sends.append((f"sale-{slugify(name)}", f"{name} Switch 2 upgrade on sale",
                          f"Sale on the Nintendo eShop (US) for {name}: {' and '.join(parts)}. Sales end without warning.",
                          f"{SITE}/upgrade-or-buy/?g={urllib.request.quote(name)}", change))
    print(f"{len(sends)} new sale(s)")
    if len(sends) > MAX_SALES:
        sys.exit(f"Refusing to send: {len(sends)} sales at once looks like a data problem.")
    token = os.environ.get("NEWSLETTER_ADMIN_TOKEN")
    for item, subject, text, url, price in sends:
        print(f"  {item}: {subject}")
        if not token:
            continue
        body = json.dumps({"site": "nintendocritic", "item": item, "change": f'sale-{new["checked"][:7]}-{price}',
                           "subject": subject, "text": text, "url": url}).encode()
        req = urllib.request.Request(API, body, {"content-type": "application/json", "authorization": f"Bearer {token}"})
        print("   ", urllib.request.urlopen(req, timeout=60).read().decode())
    if sends and not token:
        print("NEWSLETTER_ADMIN_TOKEN not set: printed only, nothing sent.")


if __name__ == "__main__":
    main()
