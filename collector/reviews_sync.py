"""Add new Switch 2 reviews from outlet RSS feeds to the Airtable Reviews table.

Only the outlet, headline and link are stored (plus the game it's for). The one-line "Summary"
is written later in our own words, never copied from the review. Reviews for games that aren't
in the Games table are skipped and listed, so a person can decide whether to add the game.

    python3 collector/reviews_sync.py --dry-run
"""

import argparse
import html
import re
import sys
import urllib.request

from common import GAMES_TABLE, REVIEWS_TABLE, Airtable, load_env

UA = "Mozilla/5.0 (compatible; NintendoCritic/1.0; +https://nintendocritic.com/about/)"

# (outlet, feed URL, function that returns the game name for a Switch 2 review, or None)
FEEDS = [
    ("Nintendo Life", "https://www.nintendolife.com/feeds/reviews",
     lambda t, link: re.split(r"\s*\(Switch 2\)|\s+[-–]\s+", re.sub(r"^(Mini )?Review:\s*", "", t))[0]
     if "/reviews/nintendo-switch-2/" in link else None),
    ("Nintendo Everything", "https://nintendoeverything.com/category/reviews/feed/",
     lambda t, link: re.sub(r"\s+review for Nintendo Switch 2$", "", t) if t.endswith("review for Nintendo Switch 2") else None),
    ("Nintendo World Report", "https://www.nintendoworldreport.com/rss",
     lambda t, link: t.split("(Switch 2)")[0].strip() if "/review/" in link and "(Switch 2)" in t else None),
]

EDITION_WORDS = r"(nintendo switch 2 edition|switch 2 edition|definitive edition|complete edition|deluxe edition|" \
                r"ultimate edition|game of the year edition|goty edition|remastered|remaster)"


def key(name):
    """Loose match key: lower case, no punctuation, no edition words."""
    n = html.unescape(name).lower().replace("&", "and").replace("’", "'")
    n = re.sub(EDITION_WORDS, "", n)
    return re.sub(r"[^a-z0-9]", "", n)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def items(xml):
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def tag(t):
            m = re.search(rf"<{t}>(.*?)</{t}>", it, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        yield tag("title"), tag("link")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_env(("AIRTABLE_TOKEN",))
    at = Airtable(dry_run=args.dry_run)

    games = {}
    for r in at.all(GAMES_TABLE):
        n = r["fields"].get("Name")
        if n:
            games.setdefault(key(n), r["id"])
    have = {r["fields"].get("URL", "").replace("http://", "https://") for r in at.all(REVIEWS_TABLE)}

    new, unmatched = [], []
    for outlet, url, parse in FEEDS:
        try:
            xml = fetch(url)
        except Exception as ex:  # one dead feed shouldn't stop the others
            print(f"{outlet}: feed failed ({ex})", file=sys.stderr)
            continue
        for title, link in items(xml):
            name = parse(title, link)
            link = link.replace("http://", "https://")
            if not name or link in have:
                continue
            gid = games.get(key(name))
            if not gid:
                unmatched.append(f"{outlet}: {name}")
                continue
            have.add(link)
            new.append({"Review": f"{outlet}: {name} (Switch 2)", "Outlet": outlet, "URL": link,
                        "Played on": "Switch 2", "Game": [gid]})

    for f in new:
        print("add", f["Review"])
    for u in unmatched:
        print("no game row:", u)
    if new:
        at.create(REVIEWS_TABLE, new)
    print(f"{len(new)} new reviews, {len(unmatched)} for games not in the table" + (" (dry run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
