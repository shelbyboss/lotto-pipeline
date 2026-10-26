"""Turn raw draws into the numbers the dashboard shows."""
from __future__ import annotations

from collections import Counter
from datetime import date

from scipy.stats import binomtest, chisquare

NUMS = [f"{i:02d}" for i in range(100)]


def _chi(counts: list[int]) -> dict:
    r = chisquare(counts)
    return {"chi2": round(float(r.statistic), 2), "df": len(counts) - 1, "p": round(float(r.pvalue), 4)}


def _backtest_hot10(seq: list[str], warmup: int) -> dict:
    """Each draw, 'buy' the 10 most frequent numbers so far. Random = 10%."""
    hits = n = 0
    c = Counter(seq[:warmup])
    for i in range(warmup, len(seq)):
        top = {k for k, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:10]}
        hits += seq[i] in top
        n += 1
        c[seq[i]] += 1
    p = binomtest(hits, n, 0.10).pvalue if n else 1.0
    return {"draws": n, "hits": hits, "hit_rate": round(hits / n, 4) if n else 0, "p": round(float(p), 4)}


def summarize(rows: list[dict], payout_2d: float, warmup: int) -> dict:
    rows = sorted(rows, key=lambda r: r["draw_date"])
    seq = [r["last2"] for r in rows]
    n = len(seq)
    freq = Counter(seq)
    counts = [freq.get(k, 0) for k in NUMS]
    tens = Counter(s[0] for s in seq)
    units = Counter(s[1] for s in seq)

    last_seen = {}
    for i, s in enumerate(seq):
        last_seen[s] = i
    gap = {k: (n - 1 - last_seen[k]) if k in last_seen else None for k in NUMS}

    by_month = {}
    for m in range(1, 13):
        sub = [r["last2"] for r in rows if int(r["draw_date"][5:7]) == m]
        c = Counter(sub)
        by_month[f"{m:02d}"] = {"n": len(sub), "top": c.most_common(5)}

    per_year = Counter(r["draw_date"][:4] for r in rows)

    return {
        "draws": n,
        "first": rows[0]["draw_date"] if rows else None,
        "last": rows[-1]["draw_date"] if rows else None,
        "latest": rows[-1] if rows else None,
        "recent": rows[-20:][::-1],
        "freq": counts,
        "expected": round(n / 100, 2),
        "top": freq.most_common(10),
        "never": [k for k in NUMS if freq.get(k, 0) == 0],
        "gap": gap,
        "chi_2digit": _chi(counts),
        "chi_tens": _chi([tens.get(str(i), 0) for i in range(10)]),
        "chi_units": _chi([units.get(str(i), 0) for i in range(10)]),
        "tens": [tens.get(str(i), 0) for i in range(10)],
        "units": [units.get(str(i), 0) for i in range(10)],
        "backtest_hot10": _backtest_hot10(seq, warmup),
        "by_month": by_month,
        "per_year": dict(sorted(per_year.items())),
        "payout_2d": payout_2d,
        "expected_return_2d": round(payout_2d / 100, 3),
    }


def build_stats(thai: list[dict], lao: list[dict]) -> dict:
    return {
        "generated": date.today().isoformat(),
        # Thai: 2,000 THB prize on an 80 THB ticket = 25x
        "thai": summarize(thai, payout_2d=25, warmup=24),
        # Lao: official 2-digit payout 60x
        "lao": summarize(lao, payout_2d=60, warmup=100),
    }
