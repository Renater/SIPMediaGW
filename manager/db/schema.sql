-- Manager — call history schema
-- Target: the PostgreSQL instance shared with Homer (TimescaleDB image; plain
-- PG 15 SQL, no extension required). Dedicated database and role: bootstrap.sql.
--
-- Design decisions are grounded in 37 756 production rows analysed on 2026-09-03:
--   * call_id is never NULL but empty in 502 rows -> normalised to NULL, and no
--     unique constraint on call_id alone (it would have rejected those calls).
--   * ~20 rows share a call_id with the same timestamp: replayed pushes. The
--     replay guards below are partial unique indexes on (call_id, call_start)
--     and, for a call that never came up, on call_id: a push repeated is kept
--     once (ON CONFLICT DO NOTHING at ingestion).
--   * room is the reliable success discriminator: rows with a room average
--     153 636 received audio packets, rows without average 334.
--   * room_type is constant ("IVR") in every row: dropped, it discriminates nothing.

CREATE TABLE IF NOT EXISTS calls (
    id                  BIGSERIAL PRIMARY KEY,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- identity / correlation
    call_id             TEXT,                       -- SIP Call-ID, Homer correlation key ('' stored as NULL)
    gw_alias            TEXT,                       -- gateway SIP user (destination.destinationGw)
    gw_id               TEXT,                       -- once logParse ships it (upstream PR)
    gw_host             TEXT,

    -- what / where
    main_app            TEXT,                       -- baresip | recording | streaming
    platform            TEXT,                       -- connector key: visio, jitsi, teams…
    room                TEXT,                       -- meeting id; NULL means no conference was joined
    call_url            TEXT,

    -- endpoint (source) and dialled service (destination)
    source_uri          TEXT,
    source_name         TEXT,
    source_number       TEXT,
    source_domain       TEXT,
    destination_uri     TEXT,
    destination_room    TEXT,
    destination_domain  TEXT,
    peer_display_name   TEXT,

    -- timing. duration_s counts the service actually rendered (completed calls);
    -- occupancy_s counts gateway time consumed, whatever the outcome.
    call_start          TIMESTAMPTZ,
    call_end            TIMESTAMPTZ,
    duration_s          INTEGER,
    occupancy_s         INTEGER,
    close_reason        TEXT,
    last_event_type     TEXT,

    -- outcome, derived at ingestion (see calls_set_outcome):
    --   completed : a conference was joined
    --   failed    : technical failure before joining (codec, protocol, timeout…)
    --   ivr_only  : reached the IVR, left without joining
    --   not_established : the SIP call never came up (no callStart in the push);
    --                     call_start then holds the reception time
    outcome             TEXT NOT NULL DEFAULT 'ivr_only'
                        CHECK (outcome IN ('not_established', 'completed', 'failed', 'ivr_only')),

    dtmf_events         JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw                 JSONB NOT NULL              -- full payload: insurance against mapping gaps
);

-- What the gateway reports about the call itself, pushed since SIPMediaGW
-- #101 (samples), #102 (peer, encoders, media direction) and #105 (versions).
-- All NULL on calls pushed before: absent, not wrong. The encoder bit rate and
-- frame rate are a target, not a measurement: they stay in raw.
ALTER TABLE calls ADD COLUMN IF NOT EXISTS established      BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS peer_user_agent  TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS audio_codec      TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS video_codec      TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS video_encoder    TEXT;   -- main encoder line, as written
ALTER TABLE calls ADD COLUMN IF NOT EXISTS media_direction  JSONB;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS gw_version       TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS baresip_version  TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS baresip_patch    TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS chromium_version TEXT;
-- Summary of the periodic samples (main picture, received side):
--   video_state : ok | oneway (mediaDir sendonly/recvonly) | stalled (the
--                 picture came, then an interval fell under 5 frames/s) |
--                 no_picture (no interval reached 5 frames/s) | NULL when
--                 nothing was measured
ALTER TABLE calls ADD COLUMN IF NOT EXISTS video_state      TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS video_min_rx_fps NUMERIC(6,1);
ALTER TABLE calls ADD COLUMN IF NOT EXISTS video_low_intervals     INTEGER;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS video_keyframe_requests INTEGER;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS presentation_s   INTEGER;

ALTER TABLE calls DROP CONSTRAINT IF EXISTS calls_video_state_check;
ALTER TABLE calls ADD CONSTRAINT calls_video_state_check
    CHECK (video_state IN ('ok', 'oneway', 'stalled', 'no_picture'));
-- Replayed on a deployed database, CREATE TABLE above does not change the
-- existing constraint: redefine it.
ALTER TABLE calls DROP CONSTRAINT IF EXISTS calls_outcome_check;
ALTER TABLE calls ADD CONSTRAINT calls_outcome_check
    CHECK (outcome IN ('not_established', 'completed', 'failed', 'ivr_only'));

CREATE INDEX IF NOT EXISTS calls_call_id_idx   ON calls (call_id) WHERE call_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS calls_start_idx     ON calls (call_start);
CREATE INDEX IF NOT EXISTS calls_outcome_idx   ON calls (outcome);
CREATE INDEX IF NOT EXISTS calls_platform_idx  ON calls (platform);
CREATE INDEX IF NOT EXISTS calls_src_num_idx   ON calls (source_number);
CREATE INDEX IF NOT EXISTS calls_gw_idx        ON calls (gw_alias);
-- Replay guard: the same call pushed twice within the same second.
CREATE UNIQUE INDEX IF NOT EXISTS calls_replay_uidx
    ON calls (call_id, call_start) WHERE call_id IS NOT NULL AND call_start IS NOT NULL;
-- A call that never came up has no start of its own (the trigger gives it the
-- reception time, different on every push): its replay guard is the Call-ID.
CREATE UNIQUE INDEX IF NOT EXISTS calls_replay_unestablished_uidx
    ON calls (call_id) WHERE call_id IS NOT NULL AND NOT established;

-- One row per call x media x stream x direction. Video statistics were sent by
-- the gateway and dropped by the previous collector; here they are first-class.
CREATE TABLE IF NOT EXISTS call_media_stats (
    call_pk             BIGINT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    media               TEXT NOT NULL CHECK (media IN ('audio', 'video')),
    stream_index        INTEGER NOT NULL DEFAULT 0,
    direction           TEXT NOT NULL CHECK (direction IN ('tx', 'rx')),
    packets             BIGINT,
    errors              BIGINT,
    packet_reports      BIGINT,
    avg_bitrate_kbps    DOUBLE PRECISION,
    lost_packets        BIGINT,
    jitter_ms           DOUBLE PRECISION,
    PRIMARY KEY (call_pk, media, stream_index, direction)
);

-- Technical close reasons: everything else is a normal hang-up, including
-- "Connection reset by peer [104]" which covers 92 % of rows, successful ones included.
CREATE OR REPLACE FUNCTION is_technical_failure(p_reason TEXT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE AS $$
    SELECT p_reason IS NOT NULL AND (
        p_reason LIKE 'No common audio or video codecs%' OR
        p_reason LIKE 'Invalid argument%'   OR
        p_reason LIKE 'Protocol error%'     OR
        p_reason LIKE 'Connection timed out%' OR
        p_reason LIKE 'Local timeout%'      OR
        p_reason LIKE 'rtp stream error%')
$$;

CREATE OR REPLACE FUNCTION calls_set_outcome() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.call_id = '' THEN NEW.call_id := NULL; END IF;
    IF NEW.room = ''    THEN NEW.room := NULL;    END IF;

    -- No start: the SIP call never came up. Dated by its reception, so that
    -- it falls in a period and is counted instead of vanishing from every
    -- report (they all filter on call_start).
    IF NEW.call_start IS NULL THEN
        NEW.established := false;
        NEW.call_start := NEW.received_at;
    END IF;

    IF NOT NEW.established THEN
        NEW.outcome := 'not_established';
    ELSIF NEW.room IS NOT NULL THEN
        NEW.outcome := 'completed';
    ELSIF is_technical_failure(NEW.close_reason) THEN
        NEW.outcome := 'failed';
    ELSE
        NEW.outcome := 'ivr_only';
    END IF;

    -- Gateway time is consumed whatever the outcome; call duration only counts
    -- when a conference was actually joined.
    NEW.occupancy_s := COALESCE(NEW.occupancy_s, NEW.duration_s, 0);
    IF NEW.outcome <> 'completed' THEN NEW.duration_s := 0; END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS calls_outcome_trg ON calls;
CREATE TRIGGER calls_outcome_trg BEFORE INSERT ON calls
    FOR EACH ROW EXECUTE FUNCTION calls_set_outcome();

-- Reporting views ------------------------------------------------------------
-- monthly_service is defined in schema_reporting_lot0.sql, which owns it; an
-- earlier copy here was overwritten on every run and, between the two,
-- briefly absent.

-- Sources producing abnormal volume: a probe or a looping endpoint stands out
-- here instead of inflating a monthly total (cf. 3 914 sessions from a single
-- source on 2026-05-16). Threshold deliberately low; refine from the console.
CREATE OR REPLACE VIEW suspect_sources AS
SELECT call_start::date AS day,
       COALESCE(source_number, '(none)')     AS source_number,
       source_domain,
       COUNT(*)                                                   AS sessions,
       COUNT(*) FILTER (WHERE outcome <> 'completed')             AS not_completed,
       ROUND(AVG(occupancy_s))                                    AS avg_occupancy_s
FROM calls WHERE call_start IS NOT NULL
GROUP BY 1, 2, 3 HAVING COUNT(*) >= 100;
