"""Turn raw draws into the numbers the dashboard shows."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

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


MODELS = {
    "seasonal": "ออกบ่อยในเดือนเดียวกันของปีก่อนๆ",
    "hot": "ออกบ่อยที่สุดตลอดทั้งหมด",
    "recent": "ออกบ่อยช่วงหลัง (ถ่วงน้ำหนักงวดล่าสุด)",
    "overdue": "ไม่ออกมานานที่สุด (เลขค้าง)",
}


def _top10(score: dict[str, float]) -> list[str]:
    """Highest score first; ties broken by number so picks are reproducible."""
    return [k for k, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]


def _picks(model: str, history: list[dict], month: int, halflife: float) -> list[str]:
    """10 numbers a model would buy for `month`, using ONLY draws in `history`."""
    seq = [r["last2"] for r in history]
    score = {k: 0.0 for k in NUMS}
    if model == "seasonal":
        for r in history:
            if int(r["draw_date"][5:7]) == month:
                score[r["last2"]] += 1
    elif model == "hot":
        for s in seq:
            score[s] += 1
    elif model == "recent":
        n = len(seq)
        for i, s in enumerate(seq):
            score[s] += 0.5 ** ((n - 1 - i) / halflife)
    elif model == "overdue":
        last = {s: i for i, s in enumerate(seq)}
        score = {k: (len(seq) - last[k]) if k in last else len(seq) + 1 for k in NUMS}
    return _top10(score)


def forecast(rows: list[dict], today: date, halflife: float, min_history: int) -> dict:
    """Walk-forward monthly backtest of each model + this month's picks.

    For every month, each model picks 10 numbers using only draws BEFORE that
    month starts, then is scored on that month's draws. Random picking = 10%.
    """
    rows = sorted(rows, key=lambda r: r["draw_date"])
    months = sorted({r["draw_date"][:7] for r in rows})
    cur = f"{today.year:04d}-{today.month:02d}"
    if cur not in months:
        months.append(cur)

    table, totals = [], {m: [0, 0] for m in MODELS}
    current = None
    for ym in months:
        hist = [r for r in rows if r["draw_date"] < ym + "-01"]
        if len(hist) < min_history:
            continue
        draws = [r["last2"] for r in rows if r["draw_date"].startswith(ym)]
        row = {"month": ym, "draws": len(draws), "models": {}}
        for m in MODELS:
            pk = _picks(m, hist, int(ym[5:7]), halflife)
            hits = sum(d in pk for d in draws)
            row["models"][m] = {"picks": pk, "hits": hits}
            if ym != cur:  # only completed months count toward the score
                totals[m][0] += hits
                totals[m][1] += len(draws)
        if ym == cur:
            current = row
        else:
            table.append(row)

    score = {}
    for m, (h, n) in totals.items():
        p = binomtest(h, n, 0.10).pvalue if n else 1.0
        score[m] = {"label": MODELS[m], "hits": h, "draws": n,
                    "hit_rate": round(h / n, 4) if n else 0, "p": round(float(p), 4),
                    "months": len(table)}

    cur_month = int(cur[5:7])
    seasonal_hist = Counter(r["last2"] for r in rows
                            if int(r["draw_date"][5:7]) == cur_month and not r["draw_date"].startswith(cur))
    this_month = [r for r in rows if r["draw_date"].startswith(cur)]
    return {
        "month": cur,
        "current": current,
        "score": score,
        "history": table[-24:][::-1],
        "month_top_all_years": seasonal_hist.most_common(5),
        "month_years": len({r["draw_date"][:4] for r in rows
                            if int(r["draw_date"][5:7]) == cur_month and not r["draw_date"].startswith(cur)}),
        "month_so_far": [{"draw_date": r["draw_date"], "last2": r["last2"]} for r in this_month][::-1],
    }


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
    today = datetime.now(timezone(timedelta(hours=7))).date()  # Bangkok
    t = summarize(thai, payout_2d=25, warmup=24)   # Thai: 2,000 THB prize / 80 THB ticket = 25x
    l = summarize(lao, payout_2d=60, warmup=100)   # Lao: official 2-digit payout 60x
    t["forecast"] = forecast(thai, today, halflife=24, min_history=24)
    l["forecast"] = forecast(lao, today, halflife=60, min_history=100)
    return {"generated": today.isoformat(), "thai": t, "lao": l}
