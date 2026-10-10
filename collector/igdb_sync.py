"""Sync upcoming and recent Switch 2 releases from IGDB into the Airtable Games table.

- New games are added as Draft with Cartridge "Not announced".
- Release-date changes on existing rows are updated and written to the Change log.
- Rows a person has edited keep their Publisher; only IGDB ID and Release date are managed here.

Usage: python3 collector/igdb_sync.py [--dry-run] [--no-log-new] [--days-back N] [--days-ahead N]
"""
import argparse
import datetime as dt
import sys

from common import (CHANGELOG_TABLE, GAMES_TABLE, IGDB_SWITCH2, IGDB, Airtable, load_env, norm)

# IGDB game_type ids worth a page: main game, remake, remaster, expanded game (e.g. Switch 2 Editions), port.
KEEP_TYPES = {0, 8, 9, 10, 11}


def vague_note(human):
    return f"{human} (IGDB, no exact date)"


def fetch_releases(igdb, start, end):
    games = {}
    offset = 0
    while True:
        rows = igdb.query("release_dates", (
            "fields date,date_format,human,game.id,game.name,game.game_type,game.version_parent,"
            "game.involved_companies.company.name,game.involved_companies.publisher;"
            f" where platform = {IGDB_SWITCH2} & date >= {int(start.timestamp())} & date < {int(end.timestamp())};"
            f" sort date asc; limit 500; offset {offset};"))
        for r in rows:
            g = r.get("game") or {}
            if not g.get("name") or g.get("version_parent") or g.get("game_type", 0) not in KEEP_TYPES:
                continue  # skip DLC, bundles, deluxe/digital editions
            # date_format 0 is an exact day; anything else ("Nov 2026", "2026", "Q4 2026") is stored
            # by IGDB as the last day of that period, so keep only the human text for those.
            exact = r.get("date_format", 0) == 0
            day = dt.datetime.fromtimestamp(r["date"], dt.timezone.utc).date().isoformat() if exact else None
            pubs = [c["company"]["name"] for c in g.get("involved_companies", []) if c.get("publisher")]
            cur = games.get(g["id"])
            # A game can have several regional dates; prefer an exact one, then the earliest.
            better = not cur or (day and (not cur["date"] or day < cur["date"]))
            if better:
                games[g["id"]] = {"id": g["id"], "name": g["name"], "date": day,
                                  "human": r.get("human", ""), "publisher": ", ".join(pubs)}
        if len(rows) < 500:
            return list(games.values())
        offset += 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print changes without writing to Airtable")
    ap.add_argument("--no-log-new", action="store_true", help="don't add Change log rows for new games (first backfill)")
    ap.add_argument("--days-back", type=int, default=30)
    ap.add_argument("--days-ahead", type=int, default=180)
    args = ap.parse_args()

    load_env()
    igdb, at = IGDB(), Airtable(dry_run=args.dry_run)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    releases = fetch_releases(igdb, now - dt.timedelta(days=args.days_back), now + dt.timedelta(days=args.days_ahead))

    rows = at.all(GAMES_TABLE)
    by_igdb = {r["fields"]["IGDB ID"]: r for r in rows if r["fields"].get("IGDB ID")}
    by_name = {norm(r["fields"].get("Name", "")): r for r in rows}

    creates, updates, log = [], [], []
    for g in releases:
        row = by_igdb.get(g["id"]) or by_name.get(norm(g["name"]))
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

    at.create(GAMES_TABLE, creates)
    at.update(GAMES_TABLE, updates)
    at.create(CHANGELOG_TABLE, log)


if __name__ == "__main__":
    sys.exit(main())
