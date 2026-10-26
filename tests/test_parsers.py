from datetime import date

from pipeline.sources import parse_glo, parse_sanook

SANOOK = (
    '<html><body><h2><span>14 ตุลาคม 2569</span></h2>'
    '<div class="th"><h2 class="tag-dummy">เลขท้าย 4 ตัว</h2></div>'
    '<div class="td"><strong class="textBold">0358</strong></div>'
    '<h2>ชื่อนามสัตว์</h2>:<strong>แมวป่า</strong>'
    '<div class="td"><h3>เลขท้าย 3 ตัว</h3><strong>358</strong></div>'
    '<div class="td"><h3>เลขท้าย 2 ตัว</h3><strong>58</strong></div>'
    '</body></html>'
)

GLO = {
    "status": True,
    "response": {"result": {
        "date": "2026-10-16",
        "data": {
            "first": {"number": [{"round": 1, "value": "011781"}]},
            "last2": {"number": [{"round": 1, "value": "48"}]},
            "last3f": {"number": [{"value": "392"}, {"value": "402"}]},
            "last3b": {"number": [{"value": "171"}, {"value": "255"}]},
        },
    }},
}


def test_sanook_draw():
    assert parse_sanook(SANOOK, date(2026, 10, 14)) == {
        "draw_date": "2026-10-14", "last4": "0358", "last2": "58"}


def test_sanook_no_draw():
    assert parse_sanook("<html><body>ตรวจหวยลาว</body></html>", date(2026, 10, 17)) is None


def test_sanook_typo_trusts_4digit():
    html = SANOOK.replace("<strong>58</strong>", "<strong>65</strong>")
    assert parse_sanook(html, date(2026, 10, 14))["last2"] == "58"


def test_glo_draw():
    assert parse_glo(GLO) == {
        "draw_date": "2026-10-16", "first_prize": "011781", "last2": "48",
        "front3": "392/402", "back3": "171/255"}


def test_glo_no_draw():
    assert parse_glo({"status": True, "response": None}) is None
