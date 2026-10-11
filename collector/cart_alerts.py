"""Email the people watching a game when its cartridge type changes (the "Email me if this changes" box).

The deploy workflow saves the live site's static/carts.json before deploying, then runs this with the new build's
copy. Each change is sent once: the newsletter Worker remembers (game, change) pairs.

    python3 collector/cart_alerts.py old-carts.json public/static/carts.json
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

API = "https://newsletter.crossplayguide.workers.dev/notify"
SITE = "https://nintendocritic.com"
MAX_CHANGES = 15   # more than this in one night is a data problem, not news
WHAT = {
    "Full cartridge": "the whole game is on the cartridge, so you can play it straight away without downloading it first",
    "Game-key card": "the cartridge is only a key: you'll need to download the game before you can play it",
    "Code in a box": "the box holds a download code, not a cartridge",
}


def main():
    old_path, new_path = Path(sys.argv[1]), Path(sys.argv[2])
    if not old_path.exists() or not old_path.stat().st_size:
        print("No earlier carts.json (first run?): nothing to compare.")
        return
    old, new = json.loads(old_path.read_text()), json.loads(new_path.read_text())
    changes = [(slug, name, old[slug][1], cart) for slug, (name, cart) in new.items()
               if slug in old and cart in WHAT and old[slug][1] != cart]
    print(f"{len(changes)} cartridge change(s)")
    if len(changes) > MAX_CHANGES:
        sys.exit(f"Refusing to send: {len(changes)} changes at once looks like a data problem.")
    token = os.environ.get("NEWSLETTER_ADMIN_TOKEN")
    for slug, name, was, now in changes:
        if was in WHAT:
            text = f"{name} has changed from a {was.lower()} to a {now.lower()} on Switch 2: {WHAT[now]}."
            subject = f"{name} is now a {now.lower()}"
        else:
            text = f"{name}'s Switch 2 box is now confirmed as a {now.lower()}: {WHAT[now]}."
            subject = f"{name}: {now.lower()} confirmed"
        print(f"  {name}: {was or 'not announced'} -> {now}")
        if not token:
            continue
        body = json.dumps({"site": "nintendocritic", "item": slug, "change": f"{was or 'none'}->{now}",
                           "subject": subject, "text": text, "url": f"{SITE}/games/{slug}/"}).encode()
        req = urllib.request.Request(API, body, {"content-type": "application/json", "authorization": f"Bearer {token}"})
        print("   ", urllib.request.urlopen(req, timeout=60).read().decode())
    if changes and not token:
        print("NEWSLETTER_ADMIN_TOKEN not set: printed only, nothing sent.")


if __name__ == "__main__":
    main()
