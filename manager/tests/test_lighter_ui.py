"""
The screens carry values, not paragraphs: every hourly chart gets the hover
box, and the explanatory paragraphs once shown under the charts do not come
back through a template or a translation key. Column "?" hints stay: they are
read when wanted, not in the way.
"""

import re
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent / "front"
REMOVED = ("capProfileNote", "capProfileNoteCompare", "capDaysMeasured", "capSizingNote",
           "capPressureNote", "capCoverage", "qReasonsNote", "histNote", "setCostNote", "usersNote")


def test_every_hourly_chart_has_the_hover_box():
    for script in (FRONT / "js" / "views").glob("*.js"):
        text = script.read_text()
        for container in re.findall(r"\$\('(\w+)'\)\.innerHTML = hourlyLines\(", text):
            assert f"attachHover($('{container}'))" in text, f"{script.name}: {container} has no hover box"


def test_removed_paragraphs_stay_removed():
    templates = " ".join(p.read_text() for p in (FRONT / "views").glob("*.html"))
    dictionary = (FRONT / "js" / "i18n.js").read_text()
    for key in REMOVED:
        assert f'"{key}"' not in templates and f"'{key}'" not in templates, f"a template shows {key} again"
        assert not re.search(rf"^\s+{key}:", dictionary, re.M), f"i18n defines {key} again"
    assert 'data-i18n="note"' not in templates
