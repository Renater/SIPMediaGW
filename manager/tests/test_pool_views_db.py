"""
The day-type views against a real database.

The static checks read the SQL; only PostgreSQL can say whether GROUPING SETS
does what the views claim. Needs DATABASE_URL_TEST, skips without it. The
samples inserted lie in January 2000, outside any period the console shows,
and are deleted at the end, success or not.
"""

import os

import pytest

DSN = os.getenv("DATABASE_URL_TEST")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL_TEST not set; needs a real database")

# Four weeks starting on a Monday; at 9h every working day carries 2 calls,
# a Monday 5; nothing at other hours.
SAMPLES = """
    INSERT INTO pool_samples (ts, interval_s, free, idle, ivr, in_call)
    SELECT g, 60, 1, 1, 0,
           CASE WHEN extract(isodow FROM g) = 1 AND extract(hour FROM g) = 9 THEN 5
                WHEN extract(isodow FROM g) <= 5 AND extract(hour FROM g) = 9 THEN 2
                ELSE 0 END
      FROM generate_series('2000-01-03 00:00'::timestamptz, '2000-01-30 23:59', '1 minute') g
    ON CONFLICT (ts) DO NOTHING
"""
CLEANUP = "DELETE FROM pool_samples WHERE ts >= '2000-01-01' AND ts < '2000-02-01'"


@pytest.fixture()
def rows():
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(DSN, row_factory=dict_row) as conn, conn.cursor() as cursor:
        cursor.execute(CLEANUP)
        cursor.execute(SAMPLES)
        conn.commit()
        try:
            cursor.execute("""
                SELECT day_type, busy_avg, busy_peak, busy_p95, days
                  FROM pool_profile
                 WHERE month = '2000-01-01' AND hour = 9 ORDER BY day_type
            """)
            yield {row["day_type"]: row for row in cursor.fetchall()}
        finally:
            cursor.execute(CLEANUP)
            conn.commit()


def test_the_period_functions_give_the_view_figures():
    """
    P13: the routes read <view>_between(since, until). Over one month it must
    give exactly what the whole-history view gives for that month.
    """
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute(CLEANUP)
        cursor.execute(SAMPLES)
        try:
            for name in ("pool_profile", "pool_pressure", "hourly_concurrency"):
                # The period function leaves month empty (one row per slot);
                # the rest must match the view's month row for row.
                cursor.execute(f"""
                    SELECT count(*) FROM (
                      (SELECT to_jsonb(b) - 'month' FROM {name}_between('2000-01-01', '2000-02-01') b
                       EXCEPT SELECT to_jsonb(v) - 'month' FROM {name} v WHERE month = '2000-01-01')
                      UNION ALL
                      (SELECT to_jsonb(v) - 'month' FROM {name} v WHERE month = '2000-01-01'
                       EXCEPT SELECT to_jsonb(b) - 'month' FROM {name}_between('2000-01-01', '2000-02-01') b)) d""")
                assert cursor.fetchone()[0] == 0, f"{name}_between differs from {name}"
                cursor.execute(f"SELECT count(*) FROM {name}_between('2000-01-01', '2000-02-01')")
                assert cursor.fetchone()[0] > 0, f"{name}_between returned nothing"
        finally:
            conn.rollback()


def test_every_day_type_appears_once(rows):
    assert sorted(rows) == ["default", "friday", "monday", "saturday", "sunday",
                            "thursday", "tuesday", "wednesday"]


def test_working_days_are_computed_over_every_sample(rows):
    """
    Four Mondays at 5 among twenty working days: the working-days p95 is 5
    (a fifth of the samples), the average 2.6. An average of five weekday
    percentiles would have given 2.6 for both.
    """
    assert float(rows["monday"]["busy_avg"]) == 5 and rows["monday"]["days"] == 4
    assert float(rows["friday"]["busy_avg"]) == 2 and rows["friday"]["days"] == 4
    assert float(rows["default"]["busy_p95"]) == 5 and float(rows["default"]["busy_avg"]) == 2.6
    assert rows["default"]["days"] == 20
    assert rows["saturday"]["busy_peak"] == 0 and rows["saturday"]["days"] == 4


def test_a_period_over_several_months_gives_one_row_per_slot():
    """
    Review of 24/09: grouped by month as well, a year gave twelve rows per hour
    and the Capacity chart kept one of them at random. Over any period, one row
    per day type and hour, computed over every sample of the period.
    """
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM pool_samples WHERE ts >= '2000-01-01' AND ts < '2000-04-01'")
        cursor.execute("""
            INSERT INTO pool_samples (ts, interval_s, free, idle, ivr, in_call)
            SELECT g, 300, 1, 1, 0,
                   CASE WHEN extract(hour FROM g) = 9 AND extract(isodow FROM g) <= 5
                        THEN extract(month FROM g)::int ELSE 0 END
              FROM generate_series('2000-01-03 00:00'::timestamptz, '2000-03-26 23:59', '5 minute') g
        """)
        try:
            for name in ("pool_profile", "pool_pressure", "hourly_concurrency"):
                cursor.execute(f"""SELECT count(*), count(DISTINCT (day_type, hour))
                                     FROM {name}_between('2000-01-01', '2000-04-01')""")
                rows, slots = cursor.fetchone()
                assert rows == slots, f"{name}: {rows} rows for {slots} slots"
            cursor.execute("""SELECT busy_peak FROM pool_profile_between('2000-01-01', '2000-04-01')
                               WHERE day_type = 'default' AND hour = 9""")
            assert cursor.fetchone()[0] == 3, "the peak of the period is March's"
        finally:
            conn.rollback()
