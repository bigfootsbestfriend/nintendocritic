"""Sync upcoming and recent Switch 2 releases from IGDB into the Airtable Games table.

- New games are added as Draft with Cartridge "Not announced".
- Release-date changes on existing rows are updated and written to the Change log.
- Rows a person has edited keep their Publisher; only IGDB ID and Release date are managed here.

Usage: python3 collector/igdb_sync.py [--dry-run] [--no-log-new] [--days-back N] [--days-ahead N] [--prune]

--prune deletes untouched IGDB drafts that no longer pass the quality filter
(Status Draft, not approved, no verdict or notes written by a person).
"""
import argparse
import datetime as dt
import sys

from common import (CHANGELOG_TABLE, GAMES_TABLE, IGDB_SWITCH2, IGDB, Airtable, load_env, norm)
from quality import FIELDS, is_worth_a_page

# IGDB game_type ids worth a page: main game, remake, remaster, expanded game (e.g. Switch 2 Editions), port.
KEEP_TYPES = {0, 8, 9, 10, 11}
# IGDB release_region ids: 2 = North America, 8 = worldwide.
NA_REGIONS = {2, 8}


def vague_note(human):
    return f"{human} (IGDB, no exact date)"


RELEASE_FIELDS = ("fields date,date_format,human,release_region,game.id,game.name,game.game_type,game.version_parent,"
                  f"game.involved_companies.company.name,game.involved_companies.publisher,{FIELDS};")


def _paged(igdb, where):
    offset, out = 0, []
    while True:
        # Stable sort, or IGDB paging repeats and skips rows.
        rows = igdb.query("release_dates", f"{RELEASE_FIELDS} where {where}; sort id asc; limit 500; offset {offset};")
        out += rows
        if len(rows) < 500:
            return out
        offset += 500


def fetch_releases(igdb, start, end):
    # Pass 1: which games have a Switch 2 release inside the window.
    in_window = _paged(igdb, f"platform = {IGDB_SWITCH2} & date >= {int(start.timestamp())} & date < {int(end.timestamp())}")
    ids = sorted({r["game"]["id"] for r in in_window if r.get("game")})
    # Pass 2: every Switch 2 release date for those games, so the North American date is
    # picked even when it falls outside the window (otherwise dates flip between nightly runs).
    rows = []
    for i in range(0, len(ids), 200):
        rows += _paged(igdb, f"platform = {IGDB_SWITCH2} & game = ({','.join(map(str, ids[i:i + 200]))})")

    games = {}
    for r in rows:
        g = r.get("game") or {}
        if not g.get("name") or g.get("version_parent") or g.get("game_type", 0) not in KEEP_TYPES:
            continue  # skip DLC, bundles, deluxe/digital editions
        if not is_worth_a_page(g):
            continue  # eShop filler
        # date_format 0 is an exact day; anything else ("Nov 2026", "2026", "Q4 2026") is stored
        # by IGDB as the last day of that period, so keep only the human text for those.
        exact = r.get("date_format", 0) == 0 and r.get("date")
        day = dt.datetime.fromtimestamp(r["date"], dt.timezone.utc).date().isoformat() if exact else None
        pubs = [c["company"]["name"] for c in g.get("involved_companies", []) if c.get("publisher")]
        # Prefer the North American or worldwide date (our readers), then any exact date, then earliest.
        rank = (0 if r.get("release_region") in NA_REGIONS else 1, 0 if day else 1, r.get("date") or 10**12, r["id"])
        cur = games.get(g["id"])
        if not cur or rank < cur["rank"]:
            games[g["id"]] = {"id": g["id"], "name": g["name"], "date": day, "rank": rank,
                              "human": r.get("human", ""), "publisher": ", ".join(pubs)}
    return list(games.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print changes without writing to Airtable")
    ap.add_argument("--no-log-new", action="store_true", help="don't add Change log rows for new games (first backfill)")
    ap.add_argument("--days-back", type=int, default=30)
    ap.add_argument("--days-ahead", type=int, default=180)
    ap.add_argument("--prune", action="store_true", help="delete untouched IGDB drafts that fail the quality filter")
    args = ap.parse_args()

    load_env()
    igdb, at = IGDB(), Airtable(dry_run=args.dry_run)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    releases = fetch_releases(igdb, now - dt.timedelta(days=args.days_back), now + dt.timedelta(days=args.days_ahead))

    rows = at.all(GAMES_TABLE)
    by_igdb = {r["fields"]["IGDB ID"]: r for r in rows if r["fields"].get("IGDB ID")}
    by_name = {norm(r["fields"].get("Name", "")): r for r in rows}

    unlinked = [r for r in rows if not r["fields"].get("IGDB ID")]

    def loose_match(name):
        # Hand-added rows often use a longer or shorter title ("EA Sports Madden NFL 26" vs
        # "Madden NFL 26"). Match when one title contains the other; only for rows not yet linked.
        key = norm(name)
        hits = [r for r in unlinked if len(key) >= 10 and len(norm(r["fields"].get("Name", ""))) >= 10
                and (key in norm(r["fields"]["Name"]) or norm(r["fields"]["Name"]) in key)]
        return hits[0] if len(hits) == 1 else None

    creates, updates, log = [], [], []
    for g in releases:
        row = by_igdb.get(g["id"]) or by_name.get(norm(g["name"])) or loose_match(g["name"])
        if row in unlinked:
            unlinked.remove(row)
        if not row:
            creates.append({
                "Name": g["name"], "Status": "Draft", "Publisher": g["publisher"], "Release date": g["date"],
                "Release date note": ("From IGDB (community-edited), unconfirmed" if g["date"]
                                      else vague_note(g["human"])), "Game type": "Switch 2 game",
                "Cartridge": "Not announced", "IGDB ID": g["id"],
                "Sources": f"https://www.igdb.com/games/{g['id']} (release date, publisher)",
            })
            if not args.no_log_new:
                log.append({"Summary": f"New game: {g['name']}", "Date": today, "Type": "New game",
                            "Game": g["name"], "Details": f"Out {g['date'] or g['human']} ({g['publisher'] or 'publisher unknown'})."})
            continue
        f, change = row["fields"], {}
        if not f.get("IGDB ID"):
            change["IGDB ID"] = g["id"]
        if not f.get("Publisher") and g["publisher"]:
            change["Publisher"] = g["publisher"]
        old = f.get("Release date")
        if not g["date"]:
            # Vague IGDB date: never overwrite a real date, just note the window.
            if not old and f.get("Release date note") != vague_note(g["human"]):
                change["Release date note"] = vague_note(g["human"])
        elif old != g["date"]:
            change["Release date"] = g["date"]
            change["Release date note"] = "From IGDB (community-edited), unconfirmed"
            if old:
                log.append({"Summary": f"Release date changed: {f['Name']}", "Date": today, "Type": "Release date",
                            "Game": f["Name"], "Details": f"{old} → {g['date']} (IGDB)."})
        if change:
            updates.append((row["id"], change))

    print(f"IGDB: {len(releases)} Switch 2 games between -{args.days_back} and +{args.days_ahead} days")
    print(f"Airtable: {len(creates)} new, {len(updates)} updated, {len(log)} change-log entries"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    for c in creates:
        print(f"  + {c['Release date'] or c['Release date note']:<12}  {c['Name']}")
    names = {r["id"]: r["fields"].get("Name") for r in rows}
    for rid, ch in updates:
        print(f"  ~ {names[rid]}: {ch}")

    if args.prune:
        keep_ids = {g["id"] for g in releases}
        untouched = lambda f: (f.get("Status") == "Draft" and not f.get("Approved") and not f.get("Verdict")
                               and not f.get("We played it") and not f.get("Notes")
                               and (f.get("Sources") or "").startswith("https://www.igdb.com/"))
        # Two days' margin so games right on the window edge (time zones, rounding) are never pruned.
        window_start = (now - dt.timedelta(days=args.days_back - 2)).date().isoformat()
        # Only rows dated inside the window this run fetched; older rows weren't checked, so leave them.
        in_window = lambda f: (f.get("Release date") or "9999") >= window_start
        prune = [r for r in rows if untouched(r["fields"]) and in_window(r["fields"])
                 and r["fields"].get("IGDB ID") not in keep_ids]
        print(f"Pruning {len(prune)} untouched drafts that fail the quality filter")
        for r in prune:
            print(f"  - {r['fields'].get('Release date')}  {r['fields'].get('Name')}")
        at.delete(GAMES_TABLE, [r["id"] for r in prune])

    at.create(GAMES_TABLE, creates)
    at.update(GAMES_TABLE, updates)
    at.create(CHANGELOG_TABLE, log)


if __name__ == "__main__":
    sys.exit(main())
