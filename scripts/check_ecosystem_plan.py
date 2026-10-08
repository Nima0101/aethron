"""Offline Phase 0 planning integrity; never a product qualification check."""

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

AREA = Path("docs/engineering/aethron-ecosystem")
REQUIRED = {
    "START_HERE.md",
    "STATE.md",
    "NEXT.md",
    "PHASES.json",
    "BASELINE.md",
    "RESEARCH.md",
    "SOURCES.md",
    "ARCHITECTURE.md",
    "API-CONTRACT.md",
    "OPENAPI-PLAN.md",
    "PACKAGING.md",
    "VEHICLE-COMPATIBILITY.md",
    "MAZDA-3-2019.md",
    "DRONE-COMPATIBILITY.md",
    "SENSOR-NIGHT.md",
    "WORKFLOW.md",
    "CI-RELEASE.md",
    "TEST-EVIDENCE.md",
    "THREAT-MODEL.md",
    "ASSURANCE.md",
    "IMPLEMENTATION-BACKLOG.md",
    "PHASE1-EXECUTION-PROMPT.md",
    "HANDOFF.md",
    "OWNER-NEXT-APPLIANCE-RUNTIME.md",
    "APPLIANCE-RUNTIME.md",
    "HOME-CAMERA-COMPATIBILITY.md",
    "provenance.json",
    "versions.json",
    "baseline-protected.json",
    "evidence/checks.json",
}


class PlanError(ValueError):
    """A concrete planning-integrity failure."""


def require(condition, message):
    if not condition:
        raise PlanError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise PlanError("nonfinite JSON: " + value)


def read_json(path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (OSError, ValueError) as exc:
        raise PlanError("invalid JSON: " + path.name) from exc


def headings(text):
    """GitHub-style slugs for this plan's simple Markdown headings."""
    result = set()
    counts = {}
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            slug = re.sub(r"[^\w\- ]", "", match[1].lower()).replace(" ", "-")
            count = counts.get(slug, 0)
            counts[slug] = count + 1
            result.add(slug + ("-" + str(count) if count else ""))
    return result


def safe_relative(value):
    path = Path(value)
    require(not path.is_absolute() and ".." not in path.parts, "unsafe manifest path")
    return path


def validate(root, plan=None):
    root = root.resolve()
    plan = (plan or root / AREA).resolve()
    for name in sorted(REQUIRED):
        path = plan / name
        require(path.is_file() and path.stat().st_size > 0, "missing artifact: " + name)

    # Check every JSON artifact, including retained evidence, not only manifests.
    for path in sorted(plan.rglob("*.json")):
        read_json(path)
    phases = read_json(plan / "PHASES.json")
    require(
        phases.get("schema_version") == 1 and phases.get("project") == "AETHRON",
        "invalid phase schema/project",
    )
    require(
        type(phases.get("current_phase")) is int and phases["current_phase"] == 0,
        "Phase 0 checker cannot authorize another phase",
    )
    for flag in ("phase1_authorized", "auto_advance", "publication_authorized", "product_complete"):
        require(phases.get(flag) is False, "unsafe phase flag: " + flag)
    require(re.fullmatch(r"[a-f0-9]{40}", phases.get("baseline_sha", "")), "invalid baseline SHA")
    date.fromisoformat(phases["as_of"])
    rows = phases.get("phases", [])
    require([r.get("id") for r in rows] == list(range(6)), "phase IDs must be 0..5")
    for row in rows:
        require(type(row["id"]) is int, "invalid phase ID type")
        require(row.get("implementation_complete") is False, "product work not complete")
        require(row.get("owner") and row.get("gates"), "phase owner/gates missing")
        require(isinstance(row.get("depends_on"), list), "phase dependencies missing")
        require(
            all(type(n) is int and 0 <= n < row["id"] for n in row["depends_on"]),
            "invalid/cyclic dependency",
        )
        expected = (
            "prepared_commit_blocked"
            if row["id"] == 0
            else "awaiting_owner"
            if row["id"] == 1
            else "planned"
        )
        require(row.get("status") == expected, "unexpected phase status")
    require(
        phases.get("local_commit_status") == "blocked_by_sandbox"
        and phases.get("phase0_acceptance_complete") is False,
        "commit limitation must remain explicit until verified resolution",
    )
    require(
        rows[1]["depends_on"] == [0] and "owner_start" in rows[1]["gates"],
        "Phase 1 approval dependency missing",
    )
    appliance = phases.get("appliance_runtime", {})
    require(
        appliance.get("status") == "spec_only"
        and appliance.get("implementation_complete") is False
        and appliance.get("requires_optional_client") is False
        and appliance.get("requires_wan") is False,
        "standalone appliance must remain specified and client/WAN independent",
    )
    require(
        appliance.get("acceptance_gates") == [f"A{n:02d}" for n in range(1, 10)]
        and appliance.get("implementation_task") == "P1.7"
        and "P1.7" in rows[1]["gates"],
        "standalone boot/offline acceptance gates missing",
    )

    provenance = read_json(plan / "provenance.json")
    require(provenance.get("schema_version") == 1, "invalid provenance schema")
    sources = {}
    for source in provenance.get("sources", []):
        sid = source.get("id", "")
        require(re.fullmatch(r"S[0-9]{2,3}", sid) and sid not in sources, "invalid source ID")
        require(urlsplit(source.get("url", "")).scheme == "https", "source must use HTTPS")
        require(urlsplit(source["url"]).netloc, "source hostname missing")
        date.fromisoformat(source["retrieved"])
        require(source["retrieved"] <= phases["as_of"], "source retrieved in the future")
        require(
            source.get("version") and source.get("note") and source.get("title"),
            "source provenance incomplete",
        )
        require(
            source.get("access")
            in {"read", "api", "search_excerpt", "unavailable", "empty_dynamic"},
            "invalid source access status",
        )
        sources[sid] = source
    require(len(sources) >= 30, "research provenance missing")
    ledger = (plan / "SOURCES.md").read_text(encoding="utf-8")
    for sid, source in sources.items():
        require(
            "## " + sid + "\n" in ledger and source["url"] in ledger,
            "source ledger mismatch: " + sid,
        )

    versions = read_json(plan / "versions.json")
    require(versions.get("schema_version") == 1, "invalid version schema")
    names = set()
    for pin in versions.get("pins", []):
        name, version = pin.get("name"), pin.get("version", "")
        require(name and name not in names, "duplicate/missing pin name")
        names.add(name)
        require(
            re.fullmatch(r"(?:[0-9]+\.)+[0-9]+|[a-f0-9]{40}", version),
            "floating/invalid pin: " + name,
        )
        require(
            pin.get("status") in {"baseline", "candidate", "selected_reference", "workflow"},
            "invalid pin status",
        )
        require(pin.get("source_ids") or pin.get("source_path"), "pin provenance missing")
        for sid in pin.get("source_ids", []):
            require(sid in sources, "unknown pin source: " + sid)
            require(version in sources[sid]["version"], "pin/source version mismatch")
        if pin.get("source_path"):
            path = root / safe_relative(pin["source_path"])
            require(
                path.is_file() and version in path.read_text(encoding="utf-8"),
                "local pin provenance mismatch: " + name,
            )
    require(
        {"core", "openapi", "fastapi", "actions/checkout", "actions/setup-python"} <= names,
        "required pins missing",
    )
    for item in versions.get("unresolved", []):
        require(
            item.get("name") and item.get("gate") and item.get("reason"),
            "unresolved version requires a gate and reason",
        )

    freeze = read_json(plan / "baseline-protected.json")
    require(
        freeze.get("source_sha") == phases["baseline_sha"] and freeze.get("files"),
        "baseline protection missing",
    )
    for name, digest in freeze["files"].items():
        path = root / safe_relative(name)
        require(re.fullmatch(r"[a-f0-9]{64}", digest), "invalid protected digest")
        require(
            path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            "protected baseline changed: " + name,
        )

    for path in sorted(plan.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme:
                require(parsed.scheme in {"https", "http", "mailto"}, "unexpected link scheme")
                continue
            require(not parsed.path.startswith("/"), "absolute local link")
            logical = root / AREA / path.relative_to(plan)
            destination = (logical.parent / unquote(parsed.path)).resolve()
            require(destination.is_relative_to(root), "link escapes repository")
            if destination.is_relative_to(root / AREA):
                destination = plan / destination.relative_to(root / AREA)
            require(destination.exists(), "broken link: " + path.name + " -> " + target)
            if parsed.fragment and destination.suffix == ".md":
                require(
                    unquote(parsed.fragment) in headings(destination.read_text(encoding="utf-8")),
                    "broken anchor: " + target,
                )
            if parsed.path == "SOURCES.md" and parsed.fragment:
                require(parsed.fragment.upper() in sources, "unknown citation")

    workflow = root / ".github/workflows/aethron-ecosystem-preflight.yml"
    require(workflow.is_file(), "missing planning workflow")
    workflow_text = workflow.read_text(encoding="utf-8")
    require(
        "scripts/check_ecosystem_plan.py --self-test" in workflow_text,
        "workflow must run negative tests",
    )
    require(
        "contents: read" in workflow_text and "persist-credentials: false" in workflow_text,
        "workflow permissions/credentials not constrained",
    )
    for action in re.findall(r"uses:\s*([^\s]+)", workflow_text):
        require(re.fullmatch(r"[^@]+@[a-f0-9]{40}", action), "unpinned workflow action")
        name, sha = action.split("@")
        require(
            any(p["name"] == name and p["version"] == sha for p in versions["pins"]),
            "workflow pin provenance missing",
        )
    require(
        not re.search(r"\b(?:write-all|pull_request_target)\b|secrets\.", workflow_text),
        "unsafe planning workflow privilege",
    )

    evidence = read_json(plan / "evidence/checks.json")
    require(evidence.get("source_sha") == phases["baseline_sha"], "baseline evidence SHA mismatch")
    require(evidence.get("product_qualified") is False, "planning cannot qualify product")
    for check in evidence.get("checks", []):
        require(
            check.get("status") in {"passed", "failed", "not_run", "pending"},
            "invalid check status",
        )
        require(check.get("command") and check.get("limitation"), "evidence context missing")
    require(
        any(c.get("status") == "failed" for c in evidence.get("checks", [])),
        "inherited visual failure must remain recorded",
    )
    return len(sources)


def self_test(root):
    mutations = {
        "missing artifact": lambda p: (p / "SENSOR-NIGHT.md").unlink(),
        "broken link": lambda p: (p / "NEXT.md").write_text("[bad](absent.md)\n"),
        "broken anchor": lambda p: (p / "NEXT.md").write_text("[bad](SOURCES.md#s999)\n"),
        "invalid JSON": lambda p: (p / "PHASES.json").write_text("{broken"),
        "duplicate JSON": lambda p: (p / "PHASES.json").write_text('{"a":1,"a":2}'),
        "floating pin": lambda p: mutate_json(
            p / "versions.json", lambda d: d["pins"][0].update(version="latest")
        ),
        "missing provenance": lambda p: mutate_json(
            p / "versions.json", lambda d: d["pins"][7].update(source_ids=["S999"])
        ),
        "unauthorized phase": lambda p: mutate_json(
            p / "PHASES.json", lambda d: d.update(phase1_authorized=True)
        ),
        "cyclic dependency": lambda p: mutate_json(
            p / "PHASES.json", lambda d: d["phases"][1].update(depends_on=[1])
        ),
        "altered baseline": lambda p: mutate_json(
            p / "baseline-protected.json", lambda d: d["files"].update({"AGENTS.md": "0" * 64})
        ),
        "companion dependency": lambda p: mutate_json(
            p / "PHASES.json",
            lambda d: d["appliance_runtime"].update(requires_optional_client=True),
        ),
        "missing appliance gate": lambda p: mutate_json(
            p / "PHASES.json", lambda d: d["appliance_runtime"].update(acceptance_gates=[])
        ),
    }
    with tempfile.TemporaryDirectory(prefix="aethron-plan-negative-") as temporary:
        for index, (name, mutate) in enumerate(mutations.items()):
            plan = Path(temporary) / str(index)
            shutil.copytree(root / AREA, plan)
            mutate(plan)
            try:
                validate(root, plan)
            except (PlanError, KeyError, TypeError, ValueError):
                print("PASS negative: " + name)
            else:
                raise PlanError("negative probe incorrectly passed: " + name)
    return len(mutations)


def mutate_json(path, mutation):
    value = read_json(path)
    mutation(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        count = validate(args.root)
        probes = self_test(args.root) if args.self_test else 0
    except (PlanError, OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(1, "FAIL planning integrity: " + str(exc) + "\n")
    print(
        f"PASS planning integrity: {count} sources, {probes} negative probes; NOT product qualification"
    )


if __name__ == "__main__":
    main()
