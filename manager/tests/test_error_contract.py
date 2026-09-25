"""
The front translates a refused write by matching the text of the `detail`
the back end answered (front/js/views/users.js, orgunits.js, password.js,
api.js). Nothing else binds the two: a message reworded on one side falls
back to "request failed" on the other, without a test noticing. This one
notices: every pattern the front matches must match a message the back end
can send.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACK = [ROOT / "app.py", ROOT / "auth.py", *sorted((ROOT / "api").glob("*.py"))]
FRONT = [ROOT / "front" / "js" / "api.js", ROOT / "front" / "js" / "password.js",
         *sorted((ROOT / "front" / "js" / "views").glob("*.js"))]


def backMessages():
    """Every detail the back end can answer, f-strings rendered with the
    literals of their own file standing in for {what} and a number for the rest."""
    messages = set()
    for path in BACK:
        text = path.read_text()
        literals = set(re.findall(r'"([a-z][a-z -]{1,24})"', text))
        for template in re.findall(r'(?:detail=|return )f?"([^"\n]+)"', text):
            holes = re.findall(r"\{[^}]+\}", template)
            if not holes:
                messages.add(template)
                continue
            for literal in literals | {"8"}:
                rendered = template
                for hole in holes:
                    rendered = rendered.replace(hole, "8" if hole[1:-1].isupper() or "limit" in hole
                                                or "join" in hole or "value" in hole or "id" in hole
                                                else literal)
                messages.add(rendered)
    return messages


def frontPatterns():
    patterns = []
    for path in FRONT:
        text = path.read_text()
        for pattern in re.findall(r"/((?:[^/\\\n]|\\.)+)/\.test\(detail\)", text):
            patterns.append((path.name, re.compile(pattern)))
        for literal in re.findall(r"detail === '([^']+)'", text):
            patterns.append((path.name, re.compile(re.escape(literal) + "$")))
        for literal in re.findall(r"const PASSWORD_REQUIRED = '([^']+)'", text):
            patterns.append((path.name, re.compile(re.escape(literal) + "$")))
    return patterns


def test_the_front_reads_error_messages_the_back_end_sends():
    messages = backMessages()
    patterns = frontPatterns()
    assert len(patterns) >= 15, "the front's error patterns were not found"
    orphans = [f"{name}: /{pattern.pattern}/" for name, pattern in patterns
               if not any(pattern.search(message) for message in messages)]
    assert not orphans, "front patterns that match no message of the back end:\n" + "\n".join(orphans)
