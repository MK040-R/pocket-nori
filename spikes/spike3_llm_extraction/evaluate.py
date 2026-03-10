"""
Evaluation script: loads results from results/ and scores extraction quality.

Usage:
    python evaluate.py

Outputs evaluation_report.md in the spike directory.
"""

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
REPORT_PATH = Path(__file__).parent / "evaluation_report.md"

# Heuristics
TOPIC_LABEL_MIN = 3
TOPIC_LABEL_MAX = 50
GENERIC_TOPIC_LABELS = {
    "discussion", "update", "meeting", "talk", "conversation",
    "topics", "items", "misc", "other", "general",
}
VALID_ENTITY_TYPES = {"person", "project", "company", "product"}
VALID_STATUSES = {"open", "resolved"}


def score_topics(data: dict) -> dict:
    topics = data.get("topics", [])
    if not topics:
        return {"pass": False, "reason": "No topics extracted", "count": 0, "issues": []}

    issues = []
    for t in topics:
        label = t.get("label", "")
        if not (TOPIC_LABEL_MIN <= len(label) <= TOPIC_LABEL_MAX):
            issues.append(f"Label out of length range: '{label}'")
        if label.strip().lower() in GENERIC_TOPIC_LABELS:
            issues.append(f"Generic/non-descriptive label: '{label}'")
        if t.get("status") not in VALID_STATUSES:
            issues.append(f"Invalid status on topic '{label}': {t.get('status')}")
        if not t.get("summary", "").strip():
            issues.append(f"Missing summary for topic '{label}'")

    passed = len(issues) == 0
    return {
        "pass": passed,
        "count": len(topics),
        "issues": issues,
        "reason": "All topic labels are specific and well-formed" if passed else f"{len(issues)} issue(s) found",
    }


def score_commitments(data: dict) -> dict:
    commitments = data.get("commitments", [])
    if not commitments:
        return {
            "pass": True,
            "count": 0,
            "issues": [],
            "reason": "No commitments extracted (may be valid if transcript had none)",
        }

    issues = []
    for c in commitments:
        if not c.get("text", "").strip():
            issues.append("Commitment missing text")
        if not c.get("owner", "").strip():
            issues.append(f"Commitment missing owner: '{c.get('text', '')[:60]}'")
        if c.get("status") not in VALID_STATUSES:
            issues.append(f"Invalid status on commitment: {c.get('status')}")

    passed = len(issues) == 0
    return {
        "pass": passed,
        "count": len(commitments),
        "issues": issues,
        "reason": "All commitments have owner and text" if passed else f"{len(issues)} issue(s) found",
    }


def score_entities(data: dict) -> dict:
    entities = data.get("entities", [])
    if not entities:
        return {
            "pass": False,
            "count": 0,
            "issues": [],
            "reason": "No entities extracted",
        }

    issues = []
    for e in entities:
        if e.get("type") not in VALID_ENTITY_TYPES:
            issues.append(f"Invalid entity type '{e.get('type')}' for entity '{e.get('name')}'")
        if not e.get("name", "").strip():
            issues.append("Entity missing name")
        if not isinstance(e.get("mentions"), int) or e.get("mentions", 0) < 1:
            issues.append(f"Invalid mention count for entity '{e.get('name')}'")

    passed = len(issues) == 0
    return {
        "pass": passed,
        "count": len(entities),
        "issues": issues,
        "reason": "All entities correctly classified" if passed else f"{len(issues)} issue(s) found",
    }


def evaluate_transcript(result_dir: Path) -> dict:
    name = result_dir.name
    report: dict = {"name": name, "topics": {}, "commitments": {}, "entities": {}}

    for key, score_fn in [
        ("topics", score_topics),
        ("commitments", score_commitments),
        ("entities", score_entities),
    ]:
        path = result_dir / f"{key}.json"
        if not path.exists():
            report[key] = {"pass": False, "reason": "Result file not found", "count": 0, "issues": []}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            report[key] = score_fn(data)
        except Exception as exc:
            report[key] = {"pass": False, "reason": f"Parse error: {exc}", "count": 0, "issues": []}

    return report


def pass_fail(b: bool) -> str:
    return "PASS" if b else "FAIL"


def generate_report(evaluations: list[dict]) -> str:
    lines = [
        "# Spike 3 — LLM Extraction Evaluation Report",
        "",
        "## Overview",
        "",
        f"Transcripts evaluated: {len(evaluations)}",
        "",
        "| Transcript | Topics | Commitments | Entities | Overall |",
        "|---|---|---|---|---|",
    ]

    for ev in evaluations:
        t = pass_fail(ev["topics"].get("pass", False))
        c = pass_fail(ev["commitments"].get("pass", False))
        e = pass_fail(ev["entities"].get("pass", False))
        overall = pass_fail(all(ev[k].get("pass", False) for k in ("topics", "commitments", "entities")))
        lines.append(f"| {ev['name']} | {t} | {c} | {e} | {overall} |")

    lines += ["", "---", ""]

    for ev in evaluations:
        lines += [
            f"## {ev['name']}",
            "",
        ]
        for key in ("topics", "commitments", "entities"):
            score = ev[key]
            status = pass_fail(score.get("pass", False))
            count = score.get("count", "?")
            reason = score.get("reason", "")
            lines += [
                f"### {key.capitalize()} — {status} ({count} extracted)",
                f"- {reason}",
            ]
            for issue in score.get("issues", []):
                lines.append(f"  - Issue: {issue}")
            lines.append("")

    lines += [
        "---",
        "",
        "## Evaluation Rubric",
        "",
        "### Topics",
        "- PASS: All labels are 3-50 characters, non-generic, with a non-empty summary and valid status",
        "- FAIL: Any label is too short/long, generic (e.g. 'discussion'), missing summary, or has invalid status",
        "",
        "### Commitments",
        "- PASS: Every extracted commitment has both `text` and `owner` fields populated",
        "- FAIL: Any commitment is missing owner or text; invalid status value",
        "",
        "### Entities",
        "- PASS: All entities have a name, valid type (person/project/company/product), and mention count >= 1",
        "- FAIL: Any entity has an invalid type, missing name, or zero/missing mention count",
        "",
    ]

    all_pass = all(
        all(ev[k].get("pass", False) for k in ("topics", "commitments", "entities"))
        for ev in evaluations
    )

    lines += [
        "---",
        "",
        "## Overall Result",
        "",
        f"**{'GO' if all_pass else 'CONDITIONAL GO / NO-GO'}**",
        "",
        "See `FINDINGS.md` for the full spike narrative and recommendation.",
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    result_dirs = sorted(d for d in RESULTS_DIR.iterdir() if d.is_dir())
    if not result_dirs:
        print(f"No results found in {RESULTS_DIR}. Run runner.py first.", file=sys.stderr)
        sys.exit(1)

    evaluations = [evaluate_transcript(d) for d in result_dirs]
    report = generate_report(evaluations)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Evaluation report written to: {REPORT_PATH}")

    for ev in evaluations:
        overall = all(ev[k].get("pass", False) for k in ("topics", "commitments", "entities"))
        status = "PASS" if overall else "FAIL"
        t_count = ev["topics"].get("count", 0)
        c_count = ev["commitments"].get("count", 0)
        e_count = ev["entities"].get("count", 0)
        print(
            f"  {ev['name']}: {status} "
            f"(topics={t_count}, commitments={c_count}, entities={e_count})"
        )


if __name__ == "__main__":
    main()
