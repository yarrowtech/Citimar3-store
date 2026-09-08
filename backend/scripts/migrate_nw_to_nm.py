"""One-time data migration: New Market store code "NW" -> "NM".

The code side of the rename (config.settings.STORE_CODE_TO_NAME, the frontend,
tests) is already done; this fixes documents already written to MongoDB with
the old code. Touches every collection that carries a `store_code`:
`users`, `bills`, `footfall`, `nob`, `targets` (`counters` has none).

Safe to re-run: an `updateMany({store_code: "NW"} -> "NM")` is a no-op once
there are no "NW" rows left. The `targets` unique index on
(store_code, entry_date) does not collide as long as no "NM" targets exist
yet -- the script refuses to run if any do, so a half-done migration can't
silently drop rows.

Usage:
    python scripts/migrate_nw_to_nm.py            # dry run: report only
    python scripts/migrate_nw_to_nm.py --apply    # perform the update
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient  # noqa: E402

from config.env import env  # noqa: E402

_COLLECTIONS = ["users", "bills", "footfall", "nob", "targets"]
_OLD = "NW"
_NEW = "NM"


def main(apply: bool) -> int:
    client = MongoClient(env.mongodb_uri)
    db = client[env.mongodb_db_name]
    print(f"Database: {env.mongodb_db_name}\n")

    collides = db["targets"].count_documents({"store_code": _NEW})
    if collides:
        print(
            f"ABORT: {collides} targets row(s) already have store_code={_NEW!r}. "
            "Resolve the (store_code, entry_date) uniqueness by hand before migrating."
        )
        return 2

    total_old = 0
    for coll in _COLLECTIONS:
        old = db[coll].count_documents({"store_code": _OLD})
        new = db[coll].count_documents({"store_code": _NEW})
        total_old += old
        print(f"  {coll:10s} store_code={_OLD}: {old:5d}   store_code={_NEW}: {new:5d}")

    if total_old == 0:
        print("\nNothing to migrate.")
        return 0

    if not apply:
        print(f"\nDry run. Re-run with --apply to rewrite {total_old} document(s) {_OLD} -> {_NEW}.")
        return 0

    print()
    for coll in _COLLECTIONS:
        res = db[coll].update_many({"store_code": _OLD}, {"$set": {"store_code": _NEW}})
        print(f"  {coll:10s} modified {res.modified_count}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(apply="--apply" in sys.argv[1:]))
