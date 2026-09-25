"""
Check the SQL against the schema, without a database.

The fourth failure of that afternoon was a column name: `monthly_concurrency`
read `MAX(peak)` from a view whose column is `peak_concurrent`. Calling the route
cannot catch that — the query only fails once PostgreSQL parses it — and running
the suite against a live database would mean every contributor needs one.

So the schema files are read as the source of truth: every table and view they
declare, and the columns each one exposes. Anything the API selects has to exist
there.

What this cannot see: a column that exists in the schema files but not in the
deployed database, because a migration was never applied. That gap belongs to the
deployment procedure, not to the test suite.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db"
API = ROOT / "api"


def applyOrder():
    """
    The schema files in the order they must be applied.

    Alphabetical order is not dependency order — `schema_rates.sql` reads a view
    that `schema_reporting_lot1.sql` creates — so the order is written down
    rather than inferred, and the loop that deploys reads the same file.
    """
    listing = (DB / "apply_order.txt").read_text().splitlines()
    return [line.strip() for line in listing
            if line.strip() and not line.strip().startswith("#")]


def schemaFiles():
    files = [DB / name for name in applyOrder()]
    assert files, "apply_order.txt lists nothing"
    return files


def test_migrate_script_reads_the_same_order():
    """
    tools/migrate.sh is the one way the schema gets applied; it must read
    db/apply_order.txt the way this file does, or the test guards an order
    nobody runs. The script is run in --dry-run, which touches nothing.
    """
    import shutil
    import subprocess

    script = ROOT / "tools" / "migrate.sh"
    assert script.exists(), "tools/migrate.sh is missing"
    assert script.stat().st_mode & 0o111, "tools/migrate.sh is not executable"
    if shutil.which("sh") is None:
        pytest.skip("no shell to run the script")
    result = subprocess.run(["sh", str(script), "--dry-run"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    listed = [line.removeprefix("would apply db/") for line in result.stdout.splitlines()]
    assert listed == applyOrder(), f"script order {listed} != apply_order.txt {applyOrder()}"


@pytest.mark.parametrize("schema", [f for f in (DB / "apply_order.txt").read_text().splitlines()
                                    if f.strip() and not f.startswith("#")])
def test_schema_file_is_replayable(schema):
    """
    One script for the lab and production means every file can run on a
    database that already has it. A bare CREATE TABLE or CREATE VIEW fails the
    second time and stops the run for the files after it.
    """
    text = stripSqlComments((DB / schema).read_text())
    bare = []
    for match in re.finditer(r"^\s*CREATE\s+(?:UNIQUE\s+)?(TABLE|VIEW|INDEX|TRIGGER|FUNCTION)\s+"
                             r"(?!IF NOT EXISTS)(\w+)", text, re.M | re.I):
        kind, name = match.group(1).upper(), match.group(2)
        # A view or trigger dropped just before is recreated, not duplicated.
        dropped = re.search(rf"DROP\s+{kind}\s+IF\s+EXISTS\s+{name}\b", text[:match.start()], re.I)
        if not dropped:
            bare.append(f"{kind} {name}")
    assert not bare, (f"{schema}: not replayable — CREATE without IF NOT EXISTS, "
                      f"OR REPLACE or a DROP IF EXISTS before it: {bare}")


def viewDefinitions():
    """Every view the schema files create, by name, comments stripped."""
    views = {}
    for path in schemaFiles():
        text = re.sub(r"--[^\n]*", "", path.read_text())
        for match in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)\s+AS\b(.*?);",
                                 text, re.S | re.I):
            views[match.group(1)] = match.group(2)
    return views


def test_a_dropped_view_takes_its_readers_first():
    """
    PostgreSQL refuses to drop a view another view reads. schema_reporting_lot1
    dropped monthly_pool_hours, which monthly_pool_cost reads: fine on an empty
    database, fatal on the deployed one — the only place a replay matters.
    Every DROP VIEW without CASCADE must come after the drops of its readers.
    """
    views = viewDefinitions()
    problems = []
    for path in schemaFiles():
        text = re.sub(r"--[^\n]*", "", path.read_text())
        for match in re.finditer(r"DROP\s+VIEW\s+IF\s+EXISTS\s+(\w+)\s*(CASCADE)?", text, re.I):
            dropped, cascade = match.group(1), match.group(2)
            if cascade:
                continue
            before = text[:match.start()]
            for reader, body in views.items():
                if reader == dropped or not re.search(rf"\b{dropped}\b", body):
                    continue
                if not re.search(rf"DROP\s+VIEW\s+IF\s+EXISTS\s+{reader}\b", before, re.I):
                    problems.append(f"{path.name} drops {dropped}, which {reader} reads")
    assert not problems, "not replayable on a deployed database: " + "; ".join(problems)


def stripSqlComments(text):
    return re.sub(r"--[^\n]*", "", text)


def test_a_function_has_one_signature():
    """
    recompute_org_units() existed twice, RETURNS BIGINT and (p_note TEXT
    DEFAULT NULL): CREATE OR REPLACE overloads instead of replacing, and the
    zero-argument call was "not unique". Across the schema files, one name,
    one argument list — or an explicit DROP FUNCTION of the old one first.
    """
    signatures = {}
    dropped = set()
    for path in schemaFiles():
        text = stripSqlComments(path.read_text())
        dropped |= {m.group(1) for m in re.finditer(r"DROP\s+FUNCTION\s+IF\s+EXISTS\s+(\w+)\s*\(", text, re.I)}
        for match in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)\s*\(([^)]*)\)", text, re.I):
            name, args = match.group(1), " ".join(match.group(2).split())
            signatures.setdefault(name, set()).add(args)
    ambiguous = {n: s for n, s in signatures.items() if len(s) > 1 and n not in dropped}
    assert not ambiguous, f"functions created with several signatures and no DROP: {ambiguous}"


def test_no_schema_file_opens_its_own_transaction():
    """tools/migrate.sh wraps the run in one transaction; a file's own COMMIT would end it early."""
    offenders = [p.name for p in schemaFiles()
                 if re.search(r"^\s*(BEGIN|COMMIT)\s*;", stripSqlComments(p.read_text()), re.M | re.I)]
    assert not offenders, f"BEGIN/COMMIT inside schema files: {offenders}"


def test_every_schema_file_is_declared():
    """
    A schema file that nobody placed in the order is a file nobody applies, or
    applies at the wrong moment. Files that are not schema — the bootstrap, a
    one-off migration, sample data — are named in the comments there.
    """
    declared = set(applyOrder())
    present = {path.name for path in DB.glob("*.sql")}
    notDeclared = present - declared
    listing = (DB / "apply_order.txt").read_text()
    undocumented = {name for name in notDeclared if name not in listing}
    assert not undocumented, (
        "schema files neither ordered nor explained in db/apply_order.txt: "
        f"{sorted(undocumented)}")
    missing = declared - present
    assert not missing, f"ordered but absent: {sorted(missing)}"


def stripComments(sql):
    return "\n".join(line.split("--")[0] for line in sql.splitlines())


@pytest.fixture(scope="module")
def schema():
    """
    Relations the schema declares, with the columns each exposes.

    Views are read through their aliases: `ROUND(...) AS busy_avg` exposes
    busy_avg, whatever the expression behind it. Tables are read from their
    column declarations.
    """
    relations = {}
    for path in schemaFiles():
        sql = stripComments(path.read_text())

        for match in re.finditer(
                r"CREATE TABLE(?: IF NOT EXISTS)? (\w+)\s*\((.*?)\n\);", sql, re.S):
            name, body = match.group(1), match.group(2)
            columns = set()
            for line in body.splitlines():
                line = line.strip()
                column = re.match(
                    r"(\w+)\s+(?:BIGSERIAL|SERIAL|TEXT|INTEGER|BIGINT|SMALLINT|"
                    r"BOOLEAN|NUMERIC|TIMESTAMPTZ|TIMESTAMP|DATE|JSONB|JSON|UUID|"
                    r"DOUBLE PRECISION|REAL|VARCHAR|CHAR|INET)", line)
                if column:
                    columns.add(column.group(1))
            relations.setdefault(name, set()).update(columns)

        for match in re.finditer(r"ALTER TABLE (\w+) ADD COLUMN(?: IF NOT EXISTS)? (\w+)", sql):
            relations.setdefault(match.group(1), set()).add(match.group(2))

        for match in re.finditer(r"CREATE(?: OR REPLACE)? VIEW (\w+) AS(.*?);", sql, re.S):
            name, body = match.group(1), match.group(2)
            # An alias names a column; a bare column in the final SELECT names
            # itself. Both forms appear in these views.
            # A view exposes a column under its alias when it has one, and under
            # its own name when it is carried through unchanged — both forms
            # appear here, and missing the second reports real columns as absent.
            columns = set(re.findall(r"\bAS\s+(\w+)", body))
            columns |= set(re.findall(r"\b\w+\.(\w+)\s*(?:,|$)", body, re.M))
            columns |= set(re.findall(r"SELECT\s+([a-z_]\w*)\s*(?:,|$)", body, re.M | re.I))
            # A column carried through on its own line: `source_domain,`
            columns |= set(re.findall(r"^\s*([a-z_]\w*)\s*,\s*$", body, re.M))
            columns = {c.split(".")[-1] for c in columns}
            relations.setdefault(name, set()).update(columns)

        # A function returning a table is read like a relation: its columns
        # are the ones RETURNS TABLE declares.
        for match in re.finditer(r"CREATE(?: OR REPLACE)? FUNCTION (\w+)\s*\([^)]*\)\s*"
                                 r"RETURNS TABLE\s*\((.*?)\)\s*LANGUAGE", sql, re.S):
            columns = {part.split()[0] for part in match.group(2).split(",") if part.strip()}
            relations.setdefault(match.group(1), set()).update(columns)

    return relations


def apiQueries():
    """Every SQL string passed to fetch(), with the file and line it came from."""
    queries = []
    for path in sorted(API.glob("*.py")):
        source = path.read_text()
        # sqlWith(): {name} stands for a fixed fragment composed in by psycopg.
        for match in re.finditer(r'(?:fetch|execute)\(\s*(?:sqlWith\(\s*)?"""(.*?)"""', source, re.S):
            line = source[:match.start()].count("\n") + 1
            queries.append((f"{path.name}:{line}", re.sub(r"\{\w+\}", " ", match.group(1))))
        for match in re.finditer(r'(?:fetch|execute)\(\s*"([^"]{20,})"', source):
            line = source[:match.start()].count("\n") + 1
            queries.append((f"{path.name}:{line}", match.group(1)))
    return queries


def test_queries_are_found():
    """A guard on the guard: a regex that matches nothing would pass silently."""
    queries = apiQueries()
    assert len(queries) >= 15, f"only {len(queries)} queries found — has fetch() changed shape?"


def test_every_relation_exists(schema):
    """
    Every table and view the API reads is declared somewhere in db/.

    A name that is not there is either a typo or a migration nobody wrote.
    """
    unknown = []
    for where, query in apiQueries():
        # A CTE is a relation the query declares itself: "WITH changed AS (",
        # ", logged AS (". A write and its audit line go through them.
        declared = set(re.findall(r"(\w+)\s+AS\s*\(", query))
        # Not relations: a set-returning function ("FROM unnest(", "FROM
        # recompute_org_units("), and the right side of IS DISTINCT FROM.
        for name in re.findall(r"(?<!DISTINCT )FROM\s+(\w+)(?!\w|\s*\()|JOIN\s+(\w+)", query):
            relation = name[0] or name[1]
            if not relation or relation.lower() in ("lateral", "select") or relation in declared:
                continue
            if relation not in schema:
                unknown.append(f"{where}: {relation}")
    assert not unknown, "relations the schema does not declare:\n" + "\n".join(unknown)


SQL_KEYWORDS = set("""
select from where group order by having as and or not is null true false case when then else end
distinct filter over partition limit offset asc desc on join left right inner outer full lateral
union all with insert into values update set delete returning conflict do nothing count sum avg
min max round coalesce nullif greatest least now date extract interval cast percentile_cont
within array any some exists between like ilike in current_date current_user date_trunc to_char
epoch unnest generate_series row_number rank timestamptz integer text boolean numeric jsonb bigint
""".split())


def test_no_unknown_identifier(schema):
    """
    The one that would have caught `MAX(peak)` on `daily_peak_concurrency`.

    Every bare identifier in a query has to be a keyword, a column of one of the
    relations the query reads, an alias the query itself defines, or a named CTE.
    Anything else is a column that does not exist — which PostgreSQL only reports
    at run time, on the one route nobody happened to open.

    String literals are stripped first: 'completed' is a value, not a column, and
    counting it would produce the kind of false alarm that gets a test disabled.
    """
    problems = []
    for where, query in apiQueries():
        flat = " ".join(query.split())
        noLiterals = re.sub(r"'[^']*'", "''", flat)
        relations = {name for pair in re.findall(r"FROM\s+(\w+)|JOIN\s+(\w+)", noLiterals)
                     for name in pair if name and name.lower() != "lateral"}
        if not relations or not relations <= set(schema):
            continue
        known = set().union(*(schema[r] for r in relations))
        known |= set(re.findall(r"\bAS\s+(\w+)", noLiterals))
        known |= set(re.findall(r"WITH\s+(\w+)\s+AS", noLiterals))
        known |= relations
        for identifier in re.findall(r"(?<![.\w])([a-z][a-z0-9_]{2,})\b(?!\s*\()", noLiterals):
            if identifier in SQL_KEYWORDS or identifier in known:
                continue
            problems.append(f"{where}: '{identifier}' is not a column of {sorted(relations)}")
    assert not problems, "identifiers no relation exposes:\n" + "\n".join(sorted(set(problems)))


AGGREGATES = ("MAX", "MIN", "SUM", "AVG", "COUNT", "ROUND", "GREATEST", "LEAST")


def test_aggregate_arguments_are_real_columns(schema):
    """
    The sharp one, and the only form that catches the failure it was written for.

    `MAX(peak) AS peak` on a view whose column is `peak_concurrent` survives the
    check above: the alias declares `peak` known, and the alias happens to carry
    the same name as the missing column. Inside an aggregate the ambiguity does
    not exist — SQL does not let an alias of the same SELECT be referenced there,
    so the argument is a column or it is nothing.
    """
    problems = []
    for where, query in apiQueries():
        flat = re.sub(r"'[^']*'", "''", " ".join(query.split()))
        relations = {name for pair in re.findall(r"FROM\s+(\w+)|JOIN\s+(\w+)", flat)
                     for name in pair if name and name.lower() != "lateral"}
        if not relations or not relations <= set(schema):
            continue
        known = set().union(*(schema[r] for r in relations))
        known |= set(re.findall(r"WITH\s+(\w+)\s+AS", flat))
        for aggregate in AGGREGATES:
            for argument in re.findall(rf"\b{aggregate}\s*\(([^()]*)\)", flat, re.I):
                for identifier in re.findall(r"(?<![.\w])([a-z][a-z0-9_]{2,})\b", argument):
                    if identifier in SQL_KEYWORDS or identifier in known:
                        continue
                    problems.append(
                        f"{where}: {aggregate}({identifier}) — no relation in "
                        f"{sorted(relations)} exposes {identifier}")
    assert not problems, "aggregates over columns that do not exist:\n" + "\n".join(sorted(set(problems)))


def test_no_query_interpolates_a_value():
    """
    Parameters go through psycopg, never through an f-string.

    The filter helper builds a fragment of SQL from a fixed set of clauses and
    passes the values separately; anything else formatting a value into a query
    is an injection waiting for a curious query string.
    """
    offenders = []
    for path in sorted(API.glob("*.py")):
        source = path.read_text()
        for match in re.finditer(r'fetch\(\s*f"""', source):
            offenders.append(f"{path.name}:{source[:match.start()].count(chr(10)) + 1}")
        for match in re.finditer(r'fetch\(\s*f"', source):
            offenders.append(f"{path.name}:{source[:match.start()].count(chr(10)) + 1}")
    assert not offenders, "queries built with an f-string:\n" + "\n".join(offenders)


def test_views_are_created_after_what_they_read(schema):
    """
    A view reading another must be created after it, and dropped before it.

    PostgreSQL refuses to drop a relation something depends on — which is how
    replaying one of these files came to fail halfway, leaving the transaction
    rolled back and the schema untouched.
    """
    order, drops = [], {}
    for path in schemaFiles():
        sql = stripComments(path.read_text())
        for match in re.finditer(r"CREATE(?: OR REPLACE)? VIEW (\w+) AS(.*?);", sql, re.S):
            order.append((match.group(1), set(re.findall(r"FROM\s+(\w+)|JOIN\s+(\w+)",
                                                         match.group(2)))))
        for index, match in enumerate(re.finditer(r"DROP VIEW(?: IF EXISTS)? (\w+)", sql)):
            drops[match.group(1)] = index

    created = set()
    late = []
    for name, sources in order:
        for pair in sources:
            source = pair[0] or pair[1]
            if source in {n for n, _ in order} and source not in created:
                late.append(f"{name} reads {source}, which is created later")
        created.add(name)
    assert not late, "\n".join(late)


DAY_TYPE_VIEWS = ("pool_profile", "pool_pressure", "hourly_concurrency")


def test_day_type_views_aggregate_both_breakdowns(schema):
    """
    Capacity reads by weekday and by group (default = Monday to Friday). Both
    come from one GROUPING SETS pass over pool_sample_days: a working-days
    percentile computed over every working-day sample, never an average of
    five weekday percentiles. Each view says over how many days a slot was
    read, and drops the group row a weekend sample has no group for.
    """
    views = viewDefinitions()
    assert "pool_sample_days" in views, "the shared day view is missing"
    assert "to_char(ts, 'day')" in views["pool_sample_days"]
    functions = functionDefinitions()
    for name in DAY_TYPE_VIEWS:
        # The computation lives in <name>_rows(); <name>_between() reads it
        # over a period, one row per slot, and the view over the whole
        # history, month by month.
        body = " ".join(functions[f"{name}_rows"].split())
        assert "FROM pool_sample_days_between(p_since, p_until)" in body, f"{name} does not read its period"
        assert "GROUPING SETS ((m, weekday, hour), (m, day_group, hour))" in body, name
        assert "CASE WHEN p_by_month THEN month END AS m" in body, name
        assert "HAVING COALESCE(weekday, day_group) IS NOT NULL" in body, name
        assert "days" in schema[f"{name}_between"], f"{name} does not expose days"
        between = " ".join(functions[f"{name}_between"].split())
        assert between == f"SELECT * FROM {name}_rows(p_since, p_until, false)", f"{name}_between groups by month"
        assert f"{name}_rows('-infinity', 'infinity', true)" in views[name], f"the view {name} is not by month"


def functionDefinitions():
    """Every SQL-language function body in the schema files, by name."""
    functions = {}
    for path in schemaFiles():
        text = re.sub(r"--[^\n]*", "", path.read_text())
        for match in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)\s*\(.*?\$\$(.*?)\$\$",
                                 text, re.S | re.I):
            functions[match.group(1)] = match.group(2)
    return functions


def test_day_types_agree_between_api_and_front():
    """The switches offer exactly the day types the route accepts, in both languages."""
    source = (API / "pool.py").read_text()
    weekdays = tuple(re.findall(r'"(\w+)"', re.search(r"WEEKDAYS = \((.*?)\)", source).group(1)))
    dayTypes = ("default",) + weekdays
    template = (ROOT / "front/views/capacity.html").read_text()
    for group in ("capDayType", "capSizingDayType"):
        block = template[template.index(f'id="{group}"'):]
        block = block[:block.index("</div>")]
        assert tuple(re.findall(r'data-daytype="(\w+)"', block)) == dayTypes, group
    dictionary = (ROOT / "front/js/i18n.js").read_text()
    for key in ("capDayTypes", "capDayShort"):
        for block in re.findall(rf"{key}: \{{(.*?)\}}", dictionary, re.S):
            assert set(re.findall(r"(\w+):", block)) == set(dayTypes), key


def test_no_query_is_assembled_by_concatenation():
    """
    Fixed fragments go into a query through sqlWith() (psycopg.sql), not by
    `+`: concatenated, bandit read each of them as a possible injection (B608),
    and an annotation cannot sit on the line where a triple-quoted query opens.
    """
    offenders = []
    for path in sorted(API.glob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'"""\s*\+|\+\s*"""', line):
                offenders.append(f"{path.name}:{number}")
    assert not offenders, "queries assembled with +:\n" + "\n".join(offenders)
