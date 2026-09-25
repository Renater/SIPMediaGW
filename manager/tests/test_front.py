"""
Check the front without a browser.

Every interface bug of one long day got through the API tests untouched: a
variable redeclared in the same scope, a template literal cut in half by a
careless edit, a filter that stopped redrawing, translation keys duplicated, a
menu entry added twice. None of them needs a browser to be caught — they are all
visible in the files.

These checks were written by hand, one at a time, as each bug appeared. Gathering
them here is the point: run by hand they only catch what someone remembers to
look for.

What this cannot see: anything about behaviour. A chart drawing the wrong series,
a filter applied to the wrong query, a colour nobody can read — all pass here.
That needs a browser, and it is not this file.
"""

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parent.parent / "front"
VIEWS = FRONT / "views"
SCRIPTS = sorted(FRONT.glob("js/*.js")) + sorted(FRONT.glob("js/views/*.js"))
TEMPLATES = [FRONT / "index.html"] + sorted(VIEWS.glob("*.html"))
STYLES = sorted(FRONT.glob("css/*.css"))


def sources():
    """Everything the browser loads, as one string, for the coarse searches."""
    return "\n".join(path.read_text() for path in SCRIPTS + TEMPLATES)


def functionBodies(text):
    """Each top-level function body, braces included, in source order."""
    bodies = []
    for match in re.finditer(r"(?:^|\n)(?:export )?(?:async )?function \w+[^\n]*\{", text):
        depth, index = 0, match.end() - 1
        while index < len(text):
            depth += text[index] == "{"
            depth -= text[index] == "}"
            index += 1
            if depth == 0:
                bodies.append(text[match.end() - 1:index])
                break
    return bodies


# --------------------------------------------------------------- templates

class Balance(HTMLParser):
    """Reports the first tag that closes something other than what is open."""

    VOID = {"meta", "input", "br", "link", "img", "hr", "source",
            "path", "circle", "line", "rect", "polyline", "use"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.error = None

    def handle_starttag(self, tag, attributes):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attributes):
        # `<rect/>` opens and closes itself. The default implementation calls
        # both handlers in turn, so the closing half popped whatever was open
        # above it — the SVG icons in the menu were reported as broken markup.
        pass

    def handle_endtag(self, tag):
        if self.error:
            return
        if not self.stack:
            self.error = f"</{tag}> closes nothing"
        elif self.stack[-1] != tag:
            self.error = f"</{tag}> closes <{self.stack[-1]}>"
        else:
            self.stack.pop()


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_is_balanced(template):
    parser = Balance()
    parser.feed(template.read_text())
    assert not parser.error, f"{template.name}: {parser.error}"
    assert not parser.stack, f"{template.name}: never closed {parser.stack}"


def test_menu_has_no_duplicate_entry():
    """
    Two runs of the same edit once left two Settings buttons, one reading
    one label and the other a synonym. Both worked; only one was meant.
    """
    views = re.findall(r'data-view="(\w+)"', (FRONT / "index.html").read_text())
    duplicates = sorted({v for v in views if views.count(v) > 1})
    assert not duplicates, f"menu entries declared twice: {duplicates}"


def test_every_menu_entry_has_a_view():
    """A menu button pointing at nothing is a dead end the user finds first."""
    registered = set(re.findall(r"^\s{2}(\w+): \{", (FRONT / "js/main.js").read_text(), re.M))
    for view in re.findall(r'data-view="(\w+)"', (FRONT / "index.html").read_text()):
        assert view in registered, f"{view} is in the menu but not registered in main.js"


def test_every_subtab_has_a_view():
    """Sub-tabs navigate the same way and break the same way."""
    registered = set(re.findall(r"^\s{2}(\w+): \{", (FRONT / "js/main.js").read_text(), re.M))
    for template in VIEWS.glob("*.html"):
        for view in re.findall(r'data-subview="(\w+)"', template.read_text()):
            assert view in registered, f"{template.name}: sub-tab {view} is not registered"


def test_login_form_never_prints_the_server_text():
    """
    The API answers in English; the screen speaks the user's language. The
    login form once printed `data.detail` as received, so the throttle message
    reached a French operator untranslated. Errors are chosen by status.
    """
    text = (FRONT / "js/main.js").read_text()
    body = next(b for b in functionBodies(text) if "'/auth/login'" in b)
    assert "data.detail" not in body, "login() prints the server's message"
    assert "loginThrottled" in body, "login() does not distinguish the throttle (429)"


def test_database_banner_is_wired():
    """
    With PostgreSQL stopped the park view stayed live and nothing said the
    reporting panels would answer 503. The banner reads /health; the three
    pieces have to be present together or the signal silently disappears.
    """
    index = (FRONT / "index.html").read_text()
    main = (FRONT / "js/main.js").read_text()
    assert 'id="dbBanner"' in index, "index.html: no database banner"
    assert "fetch('/health'" in main, "main.js: nothing probes /health"
    assert "setInterval(probeHealth" in main, "main.js: the probe is not periodic"
    showLogin = next(b for b in functionBodies(main) if "$('loginView').hidden = false" in b)
    assert "stopHealthProbe();" in showLogin, "showLogin() leaves the probe running after sign-out"
    probe = next(b for b in functionBodies(main) if "fetch('/health'" in b)
    assert "'manager'" in probe and "'database'" in probe, "the probe does not tell the Manager from the database"


def test_park_view_drops_stale_rows_when_a_refresh_fails():
    """
    After a server reboot the park kept its last table, durations ticking,
    because tick() re-rendered the stale data over the error message one
    second after load() printed it. The catch has to drop the data.
    """
    text = (FRONT / "js/views/supervision.js").read_text()
    load = next(b for b in functionBodies(text) if "'/api/gateways'" in b)
    catch = load[load.index("catch"):]
    assert "data = null;" in catch, "load() keeps stale data after a failed refresh"


def templateLiterals(text):
    """Every template literal in a module, nested ones included."""
    found = []

    def scan(source):
        i = 0
        while True:
            i = source.find("`", i)
            if i < 0:
                return
            j, depth = i + 1, 0
            while j < len(source):
                c = source[j]
                if c == "\\":
                    j += 2
                    continue
                if depth == 0 and c == "`":
                    break
                if source.startswith("${", j):
                    depth += 1
                    j += 2
                    continue
                if c == "}" and depth:
                    depth -= 1
                elif c == "`" and depth:
                    k = j + 1
                    while k < len(source) and source[k] != "`":
                        k += 2 if source[k] == "\\" else 1
                    scan(source[j:k + 1])
                    j = k + 1
                    continue
                j += 1
            found.append(source[i:j + 1])
            i = j + 1

    scan(text)
    return found


def interpolations(literal):
    """The expression inside each ${...} of one literal, nested literals skipped."""
    out, i = [], 0
    while True:
        i = literal.find("${", i)
        if i < 0:
            return out
        j, depth = i + 2, 1
        while j < len(literal) and depth:
            if literal[j] == "`":
                k = j + 1
                while literal[k] != "`":
                    k += 2 if literal[k] == "\\" else 1
                j = k + 1
                continue
            depth += literal[j] == "{"
            depth -= literal[j] == "}"
            j += 1
        out.append(literal[i + 2:j - 1])
        i = j


# A field of a data object dropped into markup as is, optionally with a
# fallback. Wrapped in any call — esc(), copyable(), nf.format() — it is
# assumed deliberate: the check has no false positive on the current code.
BARE_FIELD = re.compile(r"^\s*(row|gateway|call|entry|gw|unit|reason|s|media|item|r|v)\.\w+"
                        r"(\s*(\|\||\?\?)\s*[^<>`]*)?\s*$")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_bare_field_reaches_the_dom(script):
    """
    `class="pill ${gateway.state}"` put a proxy value into an attribute with no
    escaping — the one gap in 45 sinks, and nothing checked it. A bare field in
    markup is refused; wrap it in esc() (or a helper that does).
    """
    offenders = []
    for literal in templateLiterals(script.read_text()):
        if "<" not in literal:
            continue
        offenders += [e.strip() for e in interpolations(literal) if BARE_FIELD.match(e)]
    assert not offenders, f"{script.name}: unescaped fields in markup: {offenders}"


@pytest.mark.parametrize("script", sorted(FRONT.glob("js/views/*.js")), ids=lambda p: p.name)
def test_document_listeners_are_removed_on_unmount(script):
    """
    report.js added a click listener on document at every mount and never
    removed it: one more per visit, for the life of the page. Whatever a view
    attaches to document, unmount() detaches by the same name.
    """
    text = script.read_text()
    added = set(re.findall(r"document\.addEventListener\('(\w+)',\s*(\w+)\)", text))
    removed = set(re.findall(r"document\.removeEventListener\('(\w+)',\s*(\w+)\)", text))
    assert added <= removed, f"{script.name}: added on document, never removed: {sorted(added - removed)}"


def test_park_poll_checks_it_is_still_mounted():
    """
    A poll answered after the view was replaced wrote into elements that no
    longer existed: TypeError in the catch, again in the finally. The reply is
    dropped when the view is gone, and a slow reply does not start a second poll.
    """
    text = (FRONT / "js/views/supervision.js").read_text()
    load = next(b for b in functionBodies(text) if "'/api/gateways'" in b)
    afterAwait = load[load.index("await get('/api/gateways')"):]
    beforeRender = afterAwait[:afterAwait.index("render()")]
    assert "if (!mounted) return;" in beforeRender, "load() renders without checking mounted first"
    assert "if (loading) return;" in load, "load() can overlap itself"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_every_text_input_has_a_label(template):
    """
    Five text inputs had a placeholder and no name: a screen reader read
    "edit text". A label — visible or .sr-only — for every one, unless it is
    wrapped in a <label> already.
    """
    text = template.read_text()
    labelled = set(re.findall(r'<label[^>]*\bfor="(\w+)"', text))
    wrapped = re.findall(r"<label[^>]*>(?:(?!</label>).)*?<(?:input|select)[^>]*\bid=\"(\w+)\"", text, re.S)
    unlabelled = []
    for match in re.finditer(r'<input\b([^>]*)>', text):
        attributes = match.group(1)
        if 'type="hidden"' in attributes or "aria-label=" in attributes:
            continue
        ident = re.search(r'\bid="(\w+)"', attributes)
        if ident and ident.group(1) not in labelled and ident.group(1) not in wrapped:
            unlabelled.append(ident.group(1))
    assert not unlabelled, f"{template.name}: inputs with no label: {unlabelled}"


def test_live_regions_and_dialog_have_roles():
    """
    Messages written into the page after the fact are announced only when the
    element has a live role; a drawer that traps the user is a dialog.
    """
    index = (FRONT / "index.html").read_text()
    calls = (VIEWS / "calls.html").read_text()
    assert re.search(r'id="loginError"[^>]*role="alert"', index), "login error is not announced"
    assert re.search(r'id="toast"[^>]*role="status"', index), "toast is not announced"
    assert re.search(r'id="callDrawer"[^>]*role="dialog"[^>]*aria-modal="true"[^>]*aria-labelledby="(\w+)"', calls), \
        "the call drawer is not a labelled modal dialog"


@pytest.mark.parametrize("script", sorted(FRONT.glob("js/views/*.js")), ids=lambda p: p.name)
def test_toggled_buttons_expose_their_state(script):
    """A button whose state is only a class is a colour to a screen reader."""
    text = script.read_text()
    for match in re.finditer(r"classList\.toggle\('on'", text):
        window = text[match.start():match.start() + 240]
        assert "aria-pressed" in window or "aria-current" in window, \
            f"{script.name}: .on toggled without aria-pressed near offset {match.start()}"


def test_charts_are_named_or_decorative():
    """An <svg role="img"> with no name is an image called nothing."""
    text = (FRONT / "js/charts.js").read_text()
    for match in re.finditer(r"<svg\b[^>]*>", text):
        tag = match.group(0)
        assert 'aria-hidden="true"' in tag or "aria-label=" in tag, f"unnamed chart: {tag[:80]}"


def frenchListLength(key):
    """Number of items in a list-valued key of the French dictionary."""
    french = dictionaries()[0]
    match = re.search(rf"\b{key}:\s*\[(.*?)\]", french, re.S)
    if not match:
        return None
    return len(re.findall(r"'[^']*'|\"[^\"]*\"", match.group(1)))


@pytest.mark.parametrize("script", sorted(FRONT.glob("js/views/*.js")), ids=lambda p: p.name)
def test_colspan_matches_the_header_list(script):
    """
    Two message rows spanned 4 and 7 columns under tables of 5 and 6: the
    cell stopped short of, or overflowed, the header. Every colspan written
    into a table body equals the length of the dictionary list its header is
    drawn from — found through head('<id>Head', t().<key>), or listed here for
    the tables that draw their header by hand.
    """
    text = script.read_text()
    tables = {"callRows": "callCols", "rows": "cols", "users": "userCols"}
    tables.update(re.findall(r"head\('(\w+)Head',\s*t\(\)\.(\w+)", text))
    offenders = []
    for match in re.finditer(r"\$\('(\w+)'\)\.innerHTML\s*=(.*?);\n", text, re.S):
        key = tables.get(match.group(1))
        expected = frenchListLength(key) if key else None
        if expected is None:
            continue
        offenders += [f"#{match.group(1)}: colspan {s} for {expected} columns"
                      for s in re.findall(r'colspan="(\d+)"', match.group(2)) if int(s) != expected]
    assert not offenders, f"{script.name}: {offenders}"


def test_print_sheet_comes_last():
    """
    The print rules sat in layout.css, before components.css: every later
    screen rule with the same selector overruled them and the call drawer
    printed. Paper rules live in print.css, linked last with media="print",
    and nowhere else.
    """
    index = (FRONT / "index.html").read_text()
    sheets = re.findall(r'<link rel="stylesheet" href="/static/css/([\w-]+\.css)"([^>]*)>', index)
    assert sheets and sheets[-1][0] == "print.css" and 'media="print"' in sheets[-1][1], sheets
    elsewhere = [s.name for s in STYLES if s.name != "print.css" and "@media print" in s.read_text()]
    assert not elsewhere, f"print rules outside print.css: {elsewhere}"


FILTER_BUTTON = re.compile(r'<button[^>]*data-(?:period|daytype|metric)="[^"]*"[^>]*>')


def functionBody(text, name):
    """Body of a top-level `function name(...) {...}` (closing brace at column 0)."""
    match = re.search(rf"^(?:export )?(?:async )?function {name}\([^)]*\) \{{\n(.*?)^\}}", text, re.S | re.M)
    return match.group(1) if match else None


@pytest.mark.parametrize("template", sorted(VIEWS.glob("*.html")), ids=lambda p: p.name)
def test_no_template_presses_a_filter(template):
    """
    The templates marked their default period, day type and metric as pressed,
    while the modules kept the reader's choice across visits: back on the tab,
    the buttons said "last month" over figures of the current month. The
    module is the only one that knows; a template presses nothing.
    """
    pressed = [tag for tag in FILTER_BUTTON.findall(template.read_text()) if 'class="on"' in tag]
    assert not pressed, f"{template.name}: {pressed}"


@pytest.mark.parametrize("script", sorted(FRONT.glob("js/views/*.js")), ids=lambda p: p.name)
def test_filters_are_drawn_from_module_state(script):
    """
    A view with filter buttons draws them all in one syncControls(), from its
    module state, and calls it when it mounts (applyLanguage runs at mount).
    press() is called nowhere else, and no view toggles `.on` by hand: a
    second path is how the tabs fell out of step with the data.
    """
    text = script.read_text()
    template = (VIEWS / script.name.replace(".js", ".html"))
    if not template.exists() or not FILTER_BUTTON.search(template.read_text()):
        return
    assert "classList.toggle('on'" not in text, f"{script.name}: toggles .on outside press()"
    sync = functionBody(text, "syncControls")
    assert sync is not None, f"{script.name}: no syncControls()"
    assert "syncControls();" in (functionBody(text, "applyLanguage") or "") or \
        "setPeriod(period);" in (functionBody(text, "applyLanguage") or ""), \
        f"{script.name}: controls not redrawn on mount"
    outside = text.replace(sync, "")
    assert "press(" not in outside.replace("import { press }", ""), \
        f"{script.name}: press() called outside syncControls()"
    groups = set(re.findall(r'data-(period|daytype|metric)="', template.read_text()))
    for group in groups:
        assert f"dataset.{group}" in sync, f"{script.name}: the {group} buttons are not drawn from state"


def test_press_sets_the_aria_state():
    """press() is now the only place `.on` is set on a filter: it carries the ARIA state."""
    body = functionBody((FRONT / "js/ui.js").read_text(), "press")
    assert body and "classList.toggle('on'" in body and "aria-pressed" in body


def test_toast_is_above_the_drawer():
    """
    The copy confirmation had no z-index and showed under the call drawer,
    where the copy buttons are. It must stack above the drawer and its scrim,
    and a failed copy must not look like a success.
    """
    css = (FRONT / "css/components.css").read_text()
    def zIndex(selector):
        match = re.search(rf"^{re.escape(selector)}\s*\{{[^}}]*?z-index:\s*(\d+)", css, re.M)
        return int(match.group(1)) if match else None
    toast, drawer, scrim = zIndex(".toast"), zIndex(".drawer"), zIndex(".scrim")
    assert drawer is not None and scrim is not None, "drawer or scrim lost its z-index: update this test"
    assert toast is not None and toast > max(drawer, scrim), f"toast {toast} not above drawer {drawer}"
    assert re.search(r"^\.toast\.err\s*\{[^}]*border-color:\s*var\(--error\)", css, re.M), "no error tone for the toast"
    assert "toast(t().copyFail, 'err')" in (FRONT / "js/ui.js").read_text()


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_no_native_date_input(template):
    """
    The browser's date pickers cannot be styled and let the call log ask for an
    end before its start. Dates go through the shared calendar.
    """
    native = re.findall(r'<input[^>]*type="(?:date|datetime-local|time|month|week)"', template.read_text())
    assert not native, f"{template.name}: {native}"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_date_fields_name_the_dialog_they_open(template):
    """A date field says it opens a dialog, and that dialog exists in the same template."""
    text = template.read_text()
    for field in re.findall(r'<button[^>]*class="date-field"[^>]*>', text):
        assert 'aria-haspopup="dialog"' in field and 'aria-expanded="false"' in field, field
        controls = re.search(r'aria-controls="(\w+)"', field)
        assert controls, f"{template.name}: {field}"
        assert re.search(rf'id="{controls.group(1)}"[^>]*role="dialog"', text), \
            f"{template.name}: #{controls.group(1)} is not a dialog"


def test_calendar_cleans_up_after_itself():
    """
    The calendar listens on document while it is open. The listener goes on
    close and on destroy, and every view that creates a calendar destroys it
    on unmount — the lesson of the report view's listener, one per visit.
    """
    component = (FRONT / "js/datepicker.js").read_text()
    added = set(re.findall(r"document\.addEventListener\('(\w+)',\s*(\w+)\)", component))
    removed = set(re.findall(r"document\.removeEventListener\('(\w+)',\s*(\w+)\)", component))
    assert added and added <= removed, f"datepicker.js: {sorted(added - removed)}"
    assert "style=" not in component, "a day styled through a style attribute is dropped by the CSP"
    for script in sorted(FRONT.glob("js/views/*.js")):
        text = script.read_text()
        if "createCalendar(" in text:
            unmount = next(b for b in functionBodies(text) if "mounted = false" in b)
            assert "calendar.destroy()" in unmount, f"{script.name}: calendar not destroyed on unmount"


def test_call_window_hours_keep_the_days():
    """
    Choosing a preset, then an hour, must not reset the dates: the hour
    handlers spread the current window and change one field. And the window
    is normalised (end after start) before it is used.
    """
    text = (FRONT / "js/views/calls.js").read_text()
    for field, key in (("callFromHour", "from"), ("callToHour", "to")):
        handler = re.search(rf"\$\('{field}'\)\.addEventListener\('change', event =>\s*setRange\(\{{ \.\.\.range, {key}: ", text)
        assert handler, f"{field}: the handler does not keep the rest of the window"
    set_range = next(b for b in functionBodies(text) if "range = normalise(" in b)
    assert "drawRange()" in set_range and "reload()" in set_range
    # A preset fills the dates at once: setRange, and no panel on the way.
    assert "if (PRESETS[name]) setRange(presetRange(name), name);" in text
    assert "calendar.open(" not in set_range, "a preset must fill the dates without opening the panel"


def test_calendar_blocks_an_end_before_the_start():
    """While the last day is chosen, the days before the first are unavailable."""
    component = (FRONT / "js/datepicker.js").read_text()
    assert re.search(r"state\.picking === 'end' && key < state\.start", component)
    assert "if (blocked(key)) return;" in component


def test_calendar_handlers_survive_a_closed_panel():
    """
    The panel keeps its listeners while closed, and a mouseover still reached
    it after Valider: `state.picking` on a null state, one console error per
    mouse move. Every handler attached to the panel returns first when closed.
    """
    component = (FRONT / "js/datepicker.js").read_text()
    for name in re.findall(r"panel\.addEventListener\('\w+', (\w+)\)", component):
        body = re.search(rf"function {name}\(event\) \{{\n(.*?)\n  \}}\n", component, re.S)
        assert body, f"{name}: not found"
        code = [line for line in body.group(1).splitlines() if not line.strip().startswith("//")]
        assert code[0].strip() == "if (!state) return;", f"{name} does not start with the closed-panel guard"


# ----------------------------------------------------------------- modules

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node is not installed; the syntax check needs a real parser")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_module_parses(script, tmp_path):
    """
    The one that matters most, and the one counting braces cannot do.

    A template literal cut in half by an edit leaves the braces balanced and the
    module broken: the whole interface went silent that way, and nothing short of
    a parser noticed.
    """
    copy = tmp_path / (script.stem + ".mjs")
    copy.write_text(script.read_text())
    result = subprocess.run(["node", "--check", str(copy)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"{script.name}:\n{result.stderr}"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_redeclaration_in_the_same_scope(script):
    """
    `const units` for the filter and `const units` for the answer, in one
    function: the page stopped loading with "Identifier 'units' has already been
    declared". Function bodies are read one at a time, which is the scope that
    matters for const and let.
    """
    offenders = []
    for body in functionBodies(script.read_text()):
        # The function's own braces come off first: stripping innermost blocks
        # until nothing changes would otherwise eat the whole body and find
        # nothing at all — which is how this check silently passed on the exact
        # bug it was written for.
        top, previous = body[1:-1], None
        while top != previous:
            previous = top
            top = re.sub(r"\{[^{}]*\}", "", top)
        names = re.findall(r"\b(?:const|let)\s+(\w+)\s*=", top)
        offenders += [n for n in set(names) if names.count(n) > 1]
    assert not offenders, f"{script.name}: declared twice in one scope: {sorted(set(offenders))}"


def test_imports_resolve():
    """An import naming something no module exports fails silently in the browser."""
    exported = {}
    for script in SCRIPTS:
        text = script.read_text()
        exported[script.name] = (set(re.findall(r"export (?:async )?function (\w+)", text))
                                 | set(re.findall(r"export (?:const|let) (\w+)", text)))
    problems = []
    for script in SCRIPTS:
        for names, module in re.findall(r"import \{([^}]+)\} from '([^']+)'", script.read_text()):
            target = (script.parent / module).resolve()
            if not target.is_file():
                problems.append(f"{script.name}: no module at {module}")
                continue
            for name in (n.strip() for n in names.split(",")):
                if name not in exported.get(target.name, set()):
                    problems.append(f"{script.name}: {target.name} does not export {name}")
    assert not problems, "\n".join(problems)


def test_no_inline_style_attribute():
    """
    The page carries a strict Content-Security-Policy: a style attribute written
    from JavaScript is dropped, and the layout quietly loses whatever it carried.
    Widths go through the CSSOM instead.
    """
    offenders = [s.name for s in SCRIPTS if 'style="' in s.read_text()]
    assert not offenders, f"style attributes written from JavaScript: {offenders}"


# ------------------------------------------------------------------- views

def viewPairs():
    """Each view template with the module that mounts it."""
    pairs = []
    for template in sorted(VIEWS.glob("*.html")):
        module = FRONT / "js" / "views" / f"{template.stem}.js"
        if module.is_file():
            pairs.append((template, module))
    assert pairs, "no view found"
    return pairs


@pytest.mark.parametrize("template,module", viewPairs(), ids=lambda p: p.stem)
def test_every_element_read_exists_in_the_template(template, module):
    """
    `$('vmCost')` on an input that moved to another page returns null, and the
    line after it throws. The identifiers a module reads are checked against its
    own template and against the shell, which holds the login form and the menu.
    """
    markup = template.read_text() + (FRONT / "index.html").read_text()
    missing = [identifier for identifier in set(re.findall(r"\$\('(\w+)'\)", module.read_text()))
               if f'id="{identifier}"' not in markup]
    assert not missing, f"{module.name} reads ids that no template declares: {sorted(missing)}"


@pytest.mark.parametrize("template,module", viewPairs(), ids=lambda p: p.stem)
def test_column_headers_match_the_cells(template, module):
    """
    A header list and a row built by hand drift apart, and the table shows values
    under the wrong titles — worse than showing none. Caught three times in one
    afternoon, always the same way: a column added to one side only.

    Each table is compared with its own row. A view holding two of them, as
    Capacity and Quality both do, was otherwise measured against every row in the
    module and reported four mismatches where there were none.
    """
    dictionary = (FRONT / "js/i18n.js").read_text()
    french = dictionary[dictionary.index("fr: {"):dictionary.index("  en: {")]
    text = module.read_text()

    problems = []
    for body in functionBodies(text):
        headers = re.search(r"head\('\w+', t\(\)\.(\w+)", body)
        if not headers:
            continue
        declaration = re.search(rf"{headers.group(1)}: \[(.*?)\]", french, re.S)
        if not declaration:
            continue
        columns = len(re.findall(r"'[^']*'|\"[^\"]*\"", declaration.group(1)))
        for row in re.findall(r"`(<tr>.*?</tr>)`", body, re.S):
            # An empty-state row is one cell spanning the table, so cells are
            # counted by what they cover. Checking the span rather than skipping
            # the row also catches a colspan left behind when a column is added.
            cells = 0
            for cell in re.findall(r"<td[^>]*>", row):
                span = re.search(r'colspan="(\d+)"', cell)
                cells += int(span.group(1)) if span else 1
            if cells and cells != columns:
                problems.append(f"{module.name}: {headers.group(1)} declares {columns} "
                                f"columns, a row covers {cells}")
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------- translations

def dictionaries():
    """
    The two language blocks, each bounded by its own closing brace.

    Taking the English one to the end of the file swept up the code that follows
    it, and `lang` — a variable of the translation machinery — was reported as a
    key missing from French.
    """
    text = (FRONT / "js/i18n.js").read_text()

    def block(marker):
        start = text.index(marker)
        depth, index = 0, text.index("{", start)
        while index < len(text):
            depth += text[index] == "{"
            depth -= text[index] == "}"
            index += 1
            if depth == 0:
                return text[start:index]
        raise AssertionError(f"{marker} is never closed")

    return block("fr: {"), block("  en: {")


def keysOf(block):
    """
    Every key of the dictionary, at its top level only.

    Several keys share a line — `monthField: '…', metricHours: '…'` — so reading
    one per line finds a third of them and reports the rest as undefined. Nested
    objects are skipped by tracking depth: `outcomeContext` holds keys of its own
    that are not translations.
    """
    keys, depth = [], 0
    text = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", "''", block)
    for match in re.finditer(r"[{}]|(\w+)\s*:", text):
        token = match.group(0)
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        elif depth == 1 and match.group(1):
            keys.append(match.group(1))
    return keys


def objectLiterals(text):
    """Each `const NAME = {...}` at module level, name and block, strings blanked."""
    blanked = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", "''", text)
    for match in re.finditer(r"^(?:export )?const (\w+) = \{", blanked, re.M):
        depth, index = 0, match.end() - 1
        while index < len(blanked):
            depth += blanked[index] == "{"
            depth -= blanked[index] == "}"
            index += 1
            if depth == 0:
                yield match.group(1), blanked[match.end() - 1:index]
                break


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_duplicate_key_in_module_objects(script):
    """
    VIEWS in main.js declared `settings` twice. JavaScript keeps the last one
    and says nothing; had the two differed, one view would have quietly won.
    The dictionaries had this check; every module-level object gets it now.
    """
    offenders = []
    for name, block in objectLiterals(script.read_text()):
        keys = keysOf(block)
        offenders += [f"{name}.{k}" for k in sorted({k for k in keys if keys.count(k) > 1})]
    assert not offenders, f"{script.name}: keys declared twice: {offenders}"


def test_no_duplicate_translation_key():
    """
    A key written twice is a key one edit misses. Two rounds of the same script
    once left `setInvalid` defined twice in both languages, and the second
    quietly won.
    """
    for language, block in zip(("fr", "en"), dictionaries()):
        keys = keysOf(block)
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        assert not duplicates, f"{language}: keys defined twice: {duplicates}"


def test_both_languages_carry_the_same_keys():
    french, english = (set(keysOf(block)) for block in dictionaries())
    onlyFrench = sorted(french - english - {"fr", "en"})
    onlyEnglish = sorted(english - french - {"fr", "en"})
    assert not onlyFrench and not onlyEnglish, (
        f"missing in English: {onlyFrench}\nmissing in French: {onlyEnglish}")


def test_every_key_used_is_defined():
    """A missing key renders as `undefined` in the interface, in both languages."""
    french, english = (set(keysOf(block)) for block in dictionaries())
    text = sources()
    used = set(re.findall(r"t\(\)\.(\w+)", text)) | set(re.findall(r'data-i18n(?:-aria)?="(\w+)"', text))
    missing = sorted(used - french) + sorted(used - english)
    assert not missing, f"keys used but not defined: {sorted(set(missing))}"


def test_template_literals_are_balanced():
    """
    A regular expression trimming a key once stopped at a comma inside a template
    literal and left half of it behind; the module stopped parsing and the whole
    interface went silent.

    Counting backticks over the file is exact where a line-by-line rule is not: a
    literal legitimately spans several lines, so an odd count on one line proves
    nothing, while an odd count over the file proves one is unterminated.
    """
    for script in SCRIPTS:
        count = script.read_text().count("`")
        assert count % 2 == 0, (
            f"{script.name}: {count} backticks — a template literal is unterminated")


# --------------------------------------------------------------------- css

def test_stylesheets_are_balanced():
    for stylesheet in STYLES:
        text = stylesheet.read_text()
        assert text.count("{") == text.count("}"), f"{stylesheet.name}: unbalanced braces"


def test_no_undeclared_class():
    """
    The mirror of the orphan check. `.tag` (the verdict column) and `.link`
    (a text button) were applied by the modules and declared in no stylesheet:
    the verdict rendered as bare text, and nothing said so. Every class the
    front applies has a rule — except the ones that are only hooks for JS or
    are meant to inherit (listed).
    """
    stylesheet = "\n".join(s.read_text() for s in STYLES)
    declared = set(re.findall(r"\.([a-zA-Z][\w-]*)(?=[\s,:{.\[)])", stylesheet))
    text = sources()
    used = set()
    for group in re.findall(r'class="([^"]*)"', text):
        used |= set(re.sub(r"\$\{[^}]*\}", " ", group).split())
    used |= set(re.findall(r"classList\.(?:add|toggle)\('([\w-]+)'", text))
    # Every class the front applies today has a rule; a class that is only a
    # JS hook would be listed here, with its reason.
    hooks = set()
    undeclared = sorted(used - declared - hooks)
    assert not undeclared, f"classes applied by the front with no CSS rule: {undeclared}"


def test_no_orphan_class():
    """
    A rule nobody applies is dead weight, and the ones left behind by a removed
    block are how a stylesheet grows past reading.

    Classes built at run time — a state name interpolated into a template — are
    not visible here, so the known families are listed rather than guessed.
    """
    stylesheet = "\n".join(s.read_text() for s in STYLES)
    declared = set(re.findall(r"\.([a-zA-Z][\w-]*)(?=[\s,:{.\[])", stylesheet))
    text = sources()
    # `class="pill ${outcomeClass(row.outcome)}"` still applies `pill`: dropping
    # any attribute containing an interpolation loses the literal half of it.
    used = set()
    for group in re.findall(r'class="([^"]*)"', text):
        used |= set(re.sub(r"\$\{[^}]*\}", " ", group).split())
    used |= set(re.findall(r"classList\.(?:add|toggle|remove)\('([\w-]+)'", text))
    used |= set(re.findall(r"cls: '([\w-]+)'", text))
    # Applied from a variable: gateway states, outcome names, verdict classes.
    runtime = {"free", "idle", "ivr", "call", "gone", "other", "completed",
               "failed", "ivr_only", "good", "bad", "warn", "on", "err"}
    orphans = sorted(declared - used - runtime)
    assert not orphans, f"CSS classes nothing uses: {orphans}"
