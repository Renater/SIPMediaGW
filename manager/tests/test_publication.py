"""
Before the code goes to GitHub: the licence of the upstream repository,
no lab identifier outside the tests, every variable the code reads documented,
and the service's name and logo set by the deployment.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = [path for path in ROOT.rglob("*")
             if path.is_file() and path.suffix in {".py", ".md", ".sql", ".yml", ".sh", ".html", ".js", ".css", ".example"}
             and not {"tests", ".git", "__pycache__", "node_modules"} & set(path.relative_to(ROOT).parts)
             and path.name != "REVIEW.md"]


def test_the_licence_is_the_upstream_one():
    text = (ROOT / "LICENSE").read_text()
    assert "Apache License" in text and "Version 2.0, January 2004" in text


# Every text file that goes to the repository, the tests and their fixtures
# included: a test is published like the rest.
TEXT = {".py", ".md", ".sql", ".yml", ".sh", ".html", ".js", ".mjs", ".css", ".json", ".example", ".toml", ".ini", ".txt"}
EVERYTHING = [path for path in ROOT.rglob("*")
              if path.is_file() and (path.suffix in TEXT or path.name == "Dockerfile")
              and not {".git", "__pycache__", "node_modules"} & set(path.relative_to(ROOT).parts)
              and path.name != "REVIEW.md"]


def _unmask(*words):
    """The names this test looks for, kept out of its own text (ROT13)."""
    import codecs
    return [codecs.decode(word, "rot13") for word in words]


def test_no_lab_or_client_identifier_anywhere():
    """
    The lab's addresses and names, the deployment's brand, real organisations
    and real services: none of them belongs in a public repository, not even
    in a fixture. Examples use 192.0.2.0/24 and sample.org or example.org.
    """
    names = _unmask("znatnaryyv", "gbevzrrg", "gbev", "fancpbz", "qtsvc", "zrsfva", "eraarf",
                    "dnuvyixqvg", "ubzryno", "tbhi")
    lab = re.compile(r"172\.30\.\d|SRV-[A-Z]|\b(" + "|".join(names) + r")\b", re.I)
    found = [f"{path.relative_to(ROOT)}:{n}: {line.strip()[:80]}" for path in EVERYTHING
             for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1) if lab.search(line)]
    assert not found, "lab or client identifiers:\n" + "\n".join(found)


# French is the interface's first language and lives in its dictionary, plus
# the month names; everything else — code, comments, markup, configuration,
# tests — is written in English.
FRENCH_ALLOWED = {("front", "js", "i18n.js"), ("front", "js", "format.js"), ("brand", "logo.svg")}
FRENCH_LETTERS = re.compile("[\u00e0\u00e2\u00e7\u00e8\u00e9\u00ea\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb\u00fc\u0153"
                            "\u00c0\u00c7\u00c8\u00c9\u00ca\u00ab\u00bb]")


def test_no_french_outside_the_dictionary():
    found = [f"{path.relative_to(ROOT)}:{n}: {line.strip()[:80]}" for path in EVERYTHING
             if path.relative_to(ROOT).parts not in FRENCH_ALLOWED and path.name != "test_publication.py"
             for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
             if FRENCH_LETTERS.search(line)]
    assert not found, "French outside i18n.js:\n" + "\n".join(found)


def test_the_markup_reads_in_english_until_the_dictionary_applies():
    """The text in the HTML is the English entry: what shows before translate() runs."""
    dictionary = (ROOT / "front" / "js" / "i18n.js").read_text()
    english = dictionary[dictionary.index("  en: {"):]
    pages = [ROOT / "front" / "index.html", *sorted((ROOT / "front" / "views").glob("*.html"))]
    assert '<html lang="en">' in pages[0].read_text()
    for page in pages:
        for key, text in re.findall(r'<(?:\w+)\b[^>]*\bdata-i18n="(\w+)"[^>]*>([^<]*)</', page.read_text()):
            entry = re.search(rf"\b{key}: (['\"])(.*?)\1", english)
            assert entry, f"{page.name}: {key} has no English string"
            shown = entry.group(2).replace("\\'", "'").replace("&", "&amp;")
            assert text == shown, f"{page.name}: {key} reads {text!r}, English is {shown!r}"


def test_every_variable_the_code_reads_is_documented():
    example = (ROOT / ".env.example").read_text()
    read = set()
    for path in PUBLISHED:
        if path.suffix == ".py" and not path.relative_to(ROOT).parts[0] == "tools":
            read |= set(re.findall(r'os\.(?:getenv|environ\.get)\(\s*"([A-Z][A-Z0-9_]+)"', path.read_text()))
    missing = sorted(name for name in read if not re.search(rf"^#? *{name}=", example, re.M))
    assert not missing, f"read by the code, absent from .env.example: {missing}"


def test_the_brand_comes_from_the_deployment():
    """
    Name, tagline and logo are set per deployment, as interact's: the page
    carries placeholders only, filled from /api/me as text, never as markup.
    """
    index = (ROOT / "front" / "index.html").read_text()
    assert "R\u00e9publique" not in index and "marianne" not in index
    # Once on the sign-in card, once in the top bar: the card's title says
    # what the page is for, not the name a second time.
    assert index.count('data-brand="name"') == 2, "sign-in card and top bar"
    assert '<h1 data-i18n="loginTitle">' in index
    assert index.count('data-brand="logo"') == 2 and index.count('data-brand="tagline"') == 2
    assert all("hidden" in tag for tag in re.findall(r'<img[^>]*data-brand="logo"[^>]*>', index))
    main = (ROOT / "front" / "js" / "main.js").read_text()
    body = re.search(r"function applyBrand\(brand\) \{(.*?)\n\}", main, re.S).group(1)
    assert "textContent" in body and "innerHTML" not in body
    assert "applyBrand(session.brand)" in main


def test_brand_ships_the_product_s_own_and_keeps_the_rest_out_of_git():
    """
    SIPMediaGW's logo and icon are in the repository and named by
    .env.example; whatever a deployment adds beside them stays out of git.
    """
    ignore = (ROOT / ".gitignore").read_text().splitlines()
    assert {"brand/*", "!brand/README.md", "!brand/logo.svg", "!brand/favicon.svg"} <= set(ignore)
    for name in ("logo.svg", "favicon.svg"):
        assert (ROOT / "brand" / name).read_text().lstrip().startswith("<svg"), name
    example = (ROOT / ".env.example").read_text()
    assert "MANAGER_BRAND_LOGO=logo.svg" in example and "MANAGER_BRAND_FAVICON=favicon.svg" in example
    index = (ROOT / "front" / "index.html").read_text()
    assert '<link rel="icon" id="favicon"' in index
