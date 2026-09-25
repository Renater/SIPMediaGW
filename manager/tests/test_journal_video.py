"""
P16: the Journal shows the endpoint and the picture received; the Quality
view opens the Journal on the calls behind a count.

Route tests run on the recorder of test_api_routes (no database): they check
what reaches the SQL. The rest reads the sources, and keeps the few lists
that must agree across layers (video states, outcomes) in agreement.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "front"


# ------------------------------------------------------------------ routes

def test_a_reason_filter_is_exact_and_keeps_to_user_calls(client):  # noqa: F811
    """
    "Connection reset by peer" ends 158 normal calls too: the Quality link
    carries the reason AND the outcome, compared for equality, with the same
    user-call scope as the Quality counts.
    """
    response = client.get("/api/reporting/calls", params={
        "reason": "Connection reset by peer [104]", "outcome": "not_established"})
    assert response.status_code == 200
    query, params = client.recorder.calls[-1]
    assert "COALESCE(NULLIF(close_reason, ''), %s) = %s" in query
    assert "is_user_call(main_app)" in query
    assert "outcome = ANY(%s)" in query
    assert "Connection reset by peer [104]" in params and ["not_established"] in params
    assert "(aucune cause)" in params, "an empty reason is matched by the name Quality gives it"


def test_a_video_filter_and_the_unknown_state(client):  # noqa: F811
    client.get("/api/reporting/calls", params={"video": "stalled"})
    query, params = client.recorder.calls[-1]
    assert "video_state = ANY(%s)" in query and ["stalled"] in params
    client.get("/api/reporting/calls", params={"video": "unknown"})
    query = client.recorder.calls[-1][0]
    assert "video_state IS NULL" in query and "ANY" not in query


def test_several_values_are_accepted_together(client):  # noqa: F811
    """The Journal's lists tick any number of values: one clause each, ORed
    for the video, where "not measured" is a NULL that ANY() never matches."""
    client.get("/api/reporting/calls", params={"outcome": "failed,not_established",
                                                "video": "stalled,no_picture,unknown"})
    query, params = client.recorder.calls[-1]
    assert ["failed", "not_established"] in params
    assert ["stalled", "no_picture"] in params
    assert "(video_state = ANY(%s) OR video_state IS NULL)" in query
    assert client.get("/api/reporting/calls", params={"outcome": "failed,nope"}).status_code == 400


def test_unknown_filter_values_are_refused(client):  # noqa: F811
    assert client.get("/api/reporting/calls", params={"outcome": "nope"}).status_code == 400
    assert client.get("/api/reporting/calls", params={"video": "nope"}).status_code == 400


def test_the_search_covers_the_new_fields_and_still_the_call_id(client):  # noqa: F811
    client.get("/api/reporting/calls", params={"q": "RoomKit"})
    query, params = client.recorder.calls[-1]
    for column in ("call_id ILIKE", "peer_user_agent ILIKE", "gw_version ILIKE",
                   "baresip_patch ILIKE", "video_codec ILIKE"):
        assert column in query, column
    assert params.count("%RoomKit%") == query.count("ILIKE")


def test_quality_counts_carry_their_window(client):  # noqa: F811
    for path in ("/api/reporting/outcomes?period=2026-09", "/api/reporting/video-states?period=2026-09"):
        body = client.get(path).json()
        assert body["since"] == "2026-09-01" and body["until"] == "2026-10-01", path


def test_video_states_count_conferences_only(client):  # noqa: F811
    client.get("/api/reporting/video-states?period=2026-09")
    query = client.recorder.queriesMentioning("video_state")[-1]
    assert "outcome = 'completed'" in query
    assert "COALESCE(video_state, 'unknown')" in query


# ---------------------------------------------------------- terminal label

def test_the_terminal_label():
    from api.calls import terminalLabel
    assert terminalLabel("TANDBERG/529 (ce11.40.1.1.10bdaa53ce2) Cisco-RoomKitMini") == "Cisco-RoomKitMini"
    assert terminalLabel("Linphone/5.2.0 (belle-sip/5.2.0)") == "Linphone/5.2.0"
    assert terminalLabel("Polycom-HDX") == "Polycom-HDX"
    assert terminalLabel("") is None and terminalLabel(None) is None


# --------------------------------------------------- lists that must agree

def schemaVideoStates():
    sql = (ROOT / "db" / "schema.sql").read_text()
    check = re.search(r"CHECK \(video_state IN \(([^)]*)\)\)", sql).group(1)
    return set(re.findall(r"'(\w+)'", check))


def test_video_states_agree_across_layers():
    """Schema, mapping, API and both languages name the same states."""
    import ingest.mapping as mapping
    from api.calls import VIDEO_STATES
    states = schemaVideoStates()
    assert states == {"ok", "oneway", "stalled", "no_picture"}
    assert set(VIDEO_STATES) == states | {"unknown"}
    produced = set(re.findall(r'"(ok|oneway|stalled|no_picture|\w+)"',
                              Path(mapping.__file__).read_text().split("def sampleSummary")[1]
                              .split("def mediaDetails")[0]))
    assert states <= produced
    i18n = (FRONT / "js" / "i18n.js").read_text()
    blocks = re.findall(r"videoStates: \{([^}]*)\}", i18n)
    assert len(blocks) == 2
    for block in blocks:
        assert set(re.findall(r"(\w+):", block)) == states | {"unknown"}


def test_outcomes_agree_between_schema_and_api():
    from api.calls import OUTCOMES
    sql = (ROOT / "db" / "schema.sql").read_text()
    check = re.findall(r"CHECK \(outcome IN \(([^)]*)\)\)", sql)
    assert check and all(set(re.findall(r"'(\w+)'", c)) == set(OUTCOMES) for c in check)


# --------------------------------------------------------------- the front

def test_the_journal_shows_terminal_and_video_instead_of_call_id():
    i18n = (FRONT / "js" / "i18n.js").read_text()
    for columns in re.findall(r"callCols: \[([^\]]*)\]", i18n):
        names = re.findall(r"'([^']*)'", columns)
        assert "Call-ID" not in names and len(names) == 10
    calls = (FRONT / "js" / "views" / "calls.js").read_text()
    assert "['call_id', norm(call.call_id)]" in calls, "the Call-ID stays in the drawer"


def test_a_reason_link_carries_its_outcome():
    quality = (FRONT / "js" / "views" / "quality.js").read_text()
    assert "showCalls({ reason: row.close_reason, outcome: row.outcome })" in quality


def test_a_call_never_established_is_a_failure_whatever_its_reason():
    quality = (FRONT / "js" / "views" / "quality.js").read_text()
    assert "row.is_failure || row.outcome === 'not_established'" in quality


# ------------------------------------------------------------------ P17

def test_a_call_number_finds_the_call_whatever_the_window(client):  # noqa: F811
    """"#3197" is what the drawer shows: one call, found without its date."""
    client.get("/api/reporting/calls", params={"q": " #3197 "})
    query, params = client.recorder.calls[-1]
    assert "WHERE id = %s" in query and params == (3197,)
    assert "call_start >=" not in query, "the window must not hide the call"


def test_a_number_without_hash_is_still_a_text_search(client):  # noqa: F811
    """A bare number is a SIP number or a meeting code far more often."""
    client.get("/api/reporting/calls", params={"q": "3197"})
    assert "ILIKE" in client.recorder.calls[-1][0]


def test_the_raw_payload_downloads_as_a_file(client):  # noqa: F811
    client.recorder.rows = [{"id": 3197, "call_id": "abc@10.0.0.1;x", "call_start": None,
                             "raw": {"call": {"details": {"callId": "abc"}}}}]
    response = client.get("/api/reporting/calls/3197/raw")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="call-3197-undated-abc_10.0.0.1_x.json"' in disposition
    assert response.json() == {"call": {"details": {"callId": "abc"}}}


def test_an_unknown_call_has_no_file(client):  # noqa: F811
    client.recorder.rows = []
    assert client.get("/api/reporting/calls/999999/raw").status_code == 404


def test_the_journal_lists_offer_what_the_api_accepts():
    """The Issue and Video lists of the Journal send only values the route
    knows; a value it refused would answer 400 and empty the table."""
    from api.calls import OUTCOMES, VIDEO_STATES
    calls = (FRONT / "js" / "views" / "calls.js").read_text()
    outcomes = re.search(r"const OUTCOME_FILTERS = \[([^\]]*)\]", calls).group(1)
    videos = re.search(r"const VIDEO_FILTERS = \[([^\]]*)\]", calls).group(1)
    assert set(re.findall(r"'(\w+)'", outcomes)) == set(OUTCOMES)
    assert set(re.findall(r"'(\w+)'", videos)) == set(VIDEO_STATES)


def test_no_picture_reads_as_a_fault():
    """Seen on the lab: video arriving, never decoded. Red in both views."""
    for view in ("calls.js", "quality.js"):
        source = (FRONT / "js" / "views" / view).read_text()
        assert "no_picture: 'bad'" in source, view
