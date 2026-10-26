"""Data sources.

Thai Government Lottery: official GLO JSON API (glo.or.th).
Lao Development Lottery: per-draw result pages on sanook.com.
"""
from __future__ import annotations

import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (lotto-pipeline; +https://github.com/shelbyboss/lotto-pipeline)"
GLO_URL = "https://www.glo.or.th/api/checking/getLotteryResult"
SANOOK_URL = "https://www.sanook.com/news/laolotto/{ddmmyyyy}/"

_session = requests.Session()
_session.headers.update({"User-Agent": UA})


def _request(method: str, url: str, retries: int = 3, **kw) -> requests.Response:
    """HTTP with retry + backoff. Raises after the last failed attempt."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = _session.request(method, url, timeout=20, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            return r
        except (requests.RequestException,) as e:  # network or retryable status
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{method} {url} failed after {retries} tries: {last}")


# ---------------------------------------------------------------- Thai (GLO)

def parse_glo(payload: dict) -> dict | None:
    """Return one Thai draw row, or None when the date has no draw."""
    resp = (payload or {}).get("response") or {}
    res = resp.get("result") or {}
    data = res.get("data")
    if not data:
        return None

    def nums(key: str) -> list[str]:
        return [n["value"] for n in (data.get(key) or {}).get("number", [])]

    first, last2 = nums("first"), nums("last2")
    if len(first) != 1 or len(last2) != 1:
        return None
    row = {
        "draw_date": res["date"],
        "first_prize": first[0],
        "last2": last2[0],
        "front3": "/".join(nums("last3f")),
        "back3": "/".join(nums("last3b")),
    }
    _validate_thai(row)
    return row


def _validate_thai(row: dict) -> None:
    if not re.fullmatch(r"\d{6}", row["first_prize"]):
        raise ValueError(f"bad first_prize {row}")
    if not re.fullmatch(r"\d{2}", row["last2"]):
        raise ValueError(f"bad last2 {row}")


def fetch_thai(d: date) -> dict | None:
    body = {"date": f"{d.day:02d}", "month": f"{d.month:02d}", "year": str(d.year)}
    r = _request("POST", GLO_URL, json=body)
    r.raise_for_status()
    return parse_glo(r.json())


# ---------------------------------------------------------------- Lao (Sanook)

_RE4 = re.compile(r"เลขท้าย 4 ตัว\s*(\d{4})")
_RE2 = re.compile(r"เลขท้าย 2 ตัว\s*(\d{2})")


def parse_sanook(html: str, d: date) -> dict | None:
    """Return one Lao draw row, or None when the page has no result."""
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" "))
    m4, m2 = _RE4.search(text), _RE2.search(text)
    if not m4:
        return None
    n4 = m4.group(1)
    n2 = m2.group(1) if m2 else n4[-2:]
    if n2 != n4[-2:]:
        # Source typo: trust the 4-digit figure, it is the primary result.
        n2 = n4[-2:]
    return {"draw_date": d.isoformat(), "last4": n4, "last2": n2}


def fetch_lao(d: date) -> dict | None:
    be = d.year + 543
    url = SANOOK_URL.format(ddmmyyyy=f"{d.day:02d}{d.month:02d}{be}")
    r = _request("GET", url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return parse_sanook(r.text, d)
