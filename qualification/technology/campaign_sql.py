"""Audit-only relational aggregation; admission and capture semantics are shared."""

import hashlib
import json
import sqlite3
from contextlib import closing

from qualification.campaign import _capture_findings, _inputs

# Every submission has an ordinal. Never deduplicate attempts on insertion.
ELIGIBLE = """
    SELECT a.ordinal, a.case_id FROM attempts a
    JOIN cases c ON c.id = a.case_id
    JOIN (SELECT digest, COUNT(*) n FROM attempts GROUP BY digest) d
      ON d.digest = a.digest
    WHERE d.n = 1 AND NOT EXISTS
      (SELECT 1 FROM negatives f WHERE f.ordinal = a.ordinal)
"""


def evaluate_sql(plan_bytes, captures):
    try:
        plan, rows = _inputs(plan_bytes, captures)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_capture_campaign") from None
    cases = {case["id"]: case for case in plan["cases"]}
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript("""
            PRAGMA temp_store=MEMORY;
            CREATE TABLE cases (ordinal INTEGER PRIMARY KEY, id TEXT UNIQUE, required INTEGER);
            CREATE TABLE attempts (ordinal INTEGER PRIMARY KEY, case_id TEXT, digest TEXT, now_ms INTEGER);
            CREATE TABLE negatives (ordinal INTEGER, code TEXT);
        """)
        db.executemany(
            "INSERT INTO cases VALUES (?, ?, ?)",
            [(i, case["id"], case["minimum_captures"]) for i, case in enumerate(plan["cases"])],
        )
        for i, (case_id, raw, now) in enumerate(rows):
            db.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?)",
                (i, case_id, hashlib.sha256(raw).hexdigest(), now),
            )
            codes = (
                {"capture_unplanned"}
                if case_id not in cases
                else _capture_findings(raw, now, cases[case_id], plan["rig_sha256"])
            )
            db.executemany("INSERT INTO negatives VALUES (?, ?)", [(i, code) for code in codes])
        # ELIGIBLE is a fixed source constant; no supplied text enters SQL syntax.
        db.execute("CREATE TEMP VIEW eligible AS " + ELIGIBLE)
        findings = {row[0] for row in db.execute("SELECT DISTINCT code FROM negatives")}
        if db.execute(
            "SELECT 1 FROM attempts GROUP BY digest HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone():
            findings.add("capture_reused")
        results = [
            {"case_index": i, "required": required, "eligible": count}
            for i, required, count in db.execute("""
                SELECT c.ordinal, c.required, COUNT(e.ordinal) FROM cases c
                LEFT JOIN eligible e ON c.id = e.case_id
                GROUP BY c.ordinal, c.required ORDER BY c.ordinal
            """)
        ]
        bindings = list(
            db.execute(
                "SELECT case_id, digest, now_ms FROM attempts ORDER BY case_id, digest, now_ms"
            )
        )
    if any(row["eligible"] < row["required"] for row in results):
        findings.add("capture_coverage_missing")
    count = sum(row["eligible"] for row in results)
    capture_digest = hashlib.sha256(
        b"aethron.qualification.captures.v1\0"
        + json.dumps(bindings, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        "version": 1,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "captures_sha256": capture_digest,
        "capture_counts": {
            "submitted": len(rows),
            "eligible": count,
            "rejected": len(rows) - count,
        },
        "cases": results,
        "findings": sorted(findings),
        "declaration_coverage_complete": not findings,
        "domain_verified": False,
        "procedure_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
