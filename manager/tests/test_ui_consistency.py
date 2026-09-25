"""
Actions look like interact's, signing out is asked first, a table cell
stays a table cell, and the Journal's lists tick several values.
"""

import re
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent / "front"
CSS = "\n".join(p.read_text() for p in sorted((FRONT / "css").glob("*.css")))


def test_a_table_cell_is_never_a_flex_box():
    """
    `td { display: flex }` takes the cell out of the table: it shrank to its
    content and, on a gateway with no button, the row's hover colour left a
    white square where the cell should have been.
    """
    for rule in re.findall(r"([^{}]*\btd[^{}]*)\{([^}]*)\}", CSS):
        selector, body = rule
        if re.search(r"\btd(\.[\w-]+)*\s*$", selector.strip()):
            assert "display: flex" not in body, selector.strip()


def test_signing_out_is_confirmed():
    index = (FRONT / "index.html").read_text()
    main = (FRONT / "js" / "main.js").read_text()
    assert 'id="logoutDialog"' in index and 'value="logout"' in index
    handler = re.search(r"\$\('logout'\)\.addEventListener\('click', \(\) => \{(.*?)\n\}\);", main, re.S).group(1)
    assert "/auth/logout" not in handler, "the menu entry must only open the dialog"
    assert "returnValue !== 'logout'" in main


def test_actions_are_filled_and_backing_out_is_outlined():
    """The buttons that do something are primary; Cancel is secondary."""
    views = FRONT / "views"
    assert 'class="primary" id="accountSave"' in (views / "account.html").read_text()
    users = (views / "users.html").read_text()
    assert 'id="userAdd" class="primary"' in users
    for cancel in re.findall(r'<button[^>]*data-i18n="calCancel"[^>]*>', users):
        assert 'class="secondary"' in cancel, cancel
    assert re.search(r"button\.secondary\s*\{", CSS)


def test_the_journal_lists_tick_several_values():
    calls = (FRONT / "js" / "views" / "calls.js").read_text()
    template = (FRONT / "views" / "calls.html").read_text()
    for name in ("callOutcome", "callVideo"):
        for suffix in ("Filter", "Button", "Panel", "List"):
            assert f'id="{name}{suffix}"' in template, name + suffix
    assert "picked[key].join(',')" in calls
    # All ticked filters nothing; none ticked asks nothing.
    assert "picked[key].length < all.length" in calls
    assert "if (!picked.outcome.length || !picked.video.length)" in calls


def test_every_form_field_says_what_the_browser_may_fill():
    """
    Chrome took the last name of a new account for a username (the field just
    before a password) and would fill the administrator's own login there.
    Every input of the account forms names what it is, or says "off".
    """
    for page in (FRONT / "index.html", FRONT / "views" / "users.html", FRONT / "views" / "account.html"):
        for tag in re.findall(r"<input\b[^>]*>", page.read_text()):
            if 'type="checkbox"' in tag or 'type="search"' in tag:
                continue
            assert "autocomplete=" in tag, f"{page.name}: {tag}"


def test_a_password_change_names_its_account():
    """A password form with no username leaves the password manager guessing."""
    for page in (FRONT / "index.html", FRONT / "views" / "account.html"):
        text = page.read_text()
        form = re.search(r'<form[^>]*id="(passwordForm|accountForm)".*?</form>', text, re.S).group(0)
        assert 'autocomplete="username"' in form, page.name


def test_the_second_by_second_tick_touches_only_the_durations():
    """
    Redrawing the whole park every second replaced the text being selected
    and the button holding the keyboard focus, every second (measured: focus
    back on <body>, selection empty, 1.3 s later).
    """
    source = (FRONT / "js" / "views" / "supervision.js").read_text()
    tick = re.search(r"function tick\(\) \{(.*?)\n\}", source, re.S).group(1)
    assert "render(" not in tick and "innerHTML" not in tick
    assert "td[data-since]" in tick


def test_quality_and_capacity_open_on_the_month_under_way():
    for view in ("quality.js", "capacity.js"):
        source = (FRONT / "js" / "views" / view).read_text()
        assert re.search(r"^let period = 'month'", source, re.M), view


def test_the_menu_stays_in_view_while_the_page_scrolls():
    """
    On a long Call log or Reporting page, "My account" and "Sign out" sat at
    the foot of the page: one had to scroll down to reach them. The bar and
    the menu are sticky, the menu is the window's height under the bar, and
    the bar stays below the drawer and its scrim.
    """
    layout = (FRONT / "css" / "layout.css").read_text()
    rule = lambda sel: re.search(r"^" + re.escape(sel) + r" \{([^}]*)\}", layout, re.M).group(1)
    side, bar = rule(".side"), rule(".topbar")
    assert "position: sticky" in side and "top: var(--topbar-h)" in side
    assert "height: calc(100dvh - var(--topbar-h))" in side and "overflow-y: auto" in side
    assert "position: sticky" in bar and "height: var(--topbar-h)" in bar
    bar_z = int(re.search(r"z-index: (\d+)", bar).group(1))
    for sel in (".drawer", ".scrim"):
        z = int(re.search(re.escape(sel) + r" \{[^}]*z-index: (\d+)", CSS).group(1))
        assert bar_z < z, sel


def test_a_selection_dragged_out_of_a_field_keeps_the_dialog_open():
    """
    Selecting a first name by dragging past the edge of the dialog ended with a
    click on the backdrop, which closed the form. The backdrop closes only a
    click that also began on it.
    """
    ui = (FRONT / "js" / "ui.js").read_text()
    body = re.search(r"export function wireDialogs\(view\) \{(.*?)\n\}", ui, re.S).group(1)
    assert "pointerdown" in body and "pressedOnBackdrop" in body
    assert "event.target === dialog && pressedOnBackdrop" in body
