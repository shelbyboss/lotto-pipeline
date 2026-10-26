"""Daily incremental update.

    python -m pipeline.update            # fetch new draws since the last saved one
    python -m pipeline.update --since 2021-11-01   # backfill / re-check a range

Writes docs/data/thai.csv, docs/data/lao.csv, docs/data/stats.json, docs/data/meta.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import sources
from .stats import build_stats

DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
BKK = timezone(timedelta(hours=7))

THAI_COLS = ["draw_date", "first_prize", "last2", "front3", "back3"]
LAO_COLS = ["draw_date", "last4", "last2"]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    rows = sorted({r["draw_date"]: r for r in rows}.values(), key=lambda r: r["draw_date"])
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({c: r[c] for c in cols} for r in rows)
    tmp.replace(path)  # atomic: a crash never leaves a half-written CSV


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def update(name: str, rows: list[dict], fetch, start: date, end: date, weekdays_only: bool):
    known = {r["draw_date"] for r in rows}
    added, errors = [], []
    for d in daterange(start, end):
        if weekdays_only and d.weekday() >= 5:
            continue
        try:
            row = fetch(d)
        except Exception as e:  # one bad day must not kill the run
            errors.append(f"{d}: {e}")
            continue
        if row and row["draw_date"] not in known:
            rows.append(row)
            known.add(row["draw_date"])
            added.append(row["draw_date"])
    print(f"[{name}] checked {start}..{end}  added={len(added)}  errors={len(errors)}")
    for e in errors[:10]:
        print(f"  ! {e}", file=sys.stderr)
    return added, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, help="re-check from this date")
    args = ap.parse_args()

    today = datetime.now(BKK).date()
    DATA.mkdir(parents=True, exist_ok=True)
    thai = read_csv(DATA / "thai.csv")
    lao = read_csv(DATA / "lao.csv")

    def start_for(rows):
        if args.since:
            return args.since
        last = max((r["draw_date"] for r in rows), default="2021-11-01")
        # look back 3 days so a late-published result is still picked up
        return date.fromisoformat(last) - timedelta(days=3)

    t_add, t_err = update("thai", thai, sources.fetch_thai, start_for(thai), today, False)
    l_add, l_err = update("lao", lao, sources.fetch_lao, start_for(lao), today, True)

    write_csv(DATA / "thai.csv", thai, THAI_COLS)
    write_csv(DATA / "lao.csv", lao, LAO_COLS)

    thai = read_csv(DATA / "thai.csv")
    lao = read_csv(DATA / "lao.csv")
    (DATA / "stats.json").write_text(
        json.dumps(build_stats(thai, lao), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    meta_path = DATA / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"runs": []}
    meta["last_run"] = datetime.now(BKK).isoformat(timespec="seconds")
    meta["runs"] = (meta.get("runs", []) + [{
        "at": meta["last_run"],
        "thai_added": t_add, "lao_added": l_add,
        "errors": len(t_err) + len(l_err),
    }])[-60:]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # Fail the job only if every request failed (source down / blocked)
    total_err = len(t_err) + len(l_err)
    return 1 if total_err and not (t_add or l_add) and total_err > 5 else 0


if __name__ == "__main__":
    raise SystemExit(main())
