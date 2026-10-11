"""Names of the best-known Switch 1 games, for the library checker's autocomplete (data/switch1.json).

Only names: the checker matches them against the upgrade and compatibility lists, and anything that matches
neither simply runs on Switch 2 as it is. The list hardly changes, so it's refreshed by hand now and then:

    python3 collector/switch1_list.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IGDB, load_env  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "switch1.json"
WANT = 3000


def main():
    load_env(("IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET"))
    igdb = IGDB()
    names, seen = [], set()
    for offset in range(0, WANT, 500):
        rows = igdb.query("games", f"fields name,total_rating_count; where platforms = (130) & total_rating_count > 0 "
                                   f"& game_type = (0,8,9,10,11); sort total_rating_count desc; limit 500; offset {offset};")
        if not rows:
            break
        for r in rows:
            if r["name"].lower() not in seen:
                seen.add(r["name"].lower())
                names.append(r["name"])
    OUT.write_text(json.dumps(names, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(names)} Switch 1 games -> {OUT}")


if __name__ == "__main__":
    main()
