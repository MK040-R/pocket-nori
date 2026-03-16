"""
Pocket Nori QA Check — runs all checks against the built foundation and generates qa_report.html.

Run from the project root:
    source .venv/bin/activate
    python scripts/qa_check.py

Opens the report automatically in your browser when done.
"""

import importlib
import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

ROOT = Path(__file__).parent.parent
REPORT_PATH = ROOT / "qa_report.html"

results: list[dict] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(name: str, detail: str, passed: bool, info: str = "") -> None:
    results.append({"name": name, "detail": detail, "passed": passed, "info": info})
    icon = "✅" if passed else "❌"
    print(f"  {icon}  {name}")
    if info and not passed:
        print(f"       → {info}")


def section(title: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


# ---------------------------------------------------------------------------
# 1. Environment variables
# ---------------------------------------------------------------------------

REQUIRED_VARS = [
    ("SUPABASE_URL", "Supabase project URL"),
    ("SUPABASE_ANON_KEY", "Supabase anon key (used by app code)"),
    ("SUPABASE_SERVICE_KEY", "Supabase service key (migrations only)"),
    ("DATABASE_URL", "Direct PostgreSQL connection string"),
    ("ANTHROPIC_API_KEY", "Claude API key"),
    ("UPSTASH_REDIS_URL", "Upstash Redis URL for Celery broker"),
    ("DEEPGRAM_API_KEY", "Deepgram transcription API key"),
    ("GOOGLE_CLIENT_ID", "Google OAuth client ID"),
    ("GOOGLE_CLIENT_SECRET", "Google OAuth client secret"),
    ("SECRET_KEY", "App secret key for JWT signing"),
]

section("1 · Environment Variables")
for var, label in REQUIRED_VARS:
    val = os.getenv(var, "")
    ok = bool(val) and val != "changeme" and "placeholder" not in val.lower()
    check(var, label, ok, "Missing or placeholder value" if not ok else "")


# ---------------------------------------------------------------------------
# 2. Python imports — all src modules load without error
# ---------------------------------------------------------------------------

section("2 · Module Imports")

sys.path.insert(0, str(ROOT))

MODULES = [
    ("src.config", "Config — reads .env, validates required vars"),
    ("src.main", "FastAPI app — server entry point"),
    ("src.database", "Database — Supabase client singleton"),
    ("src.llm_client", "LLM client — AI gateway (instructor + Claude)"),
    ("src.celeryconfig", "Celery config — Redis broker setup"),
    ("src.workers.tasks", "Celery tasks — process_transcript + generate_brief"),
    ("src.workers.extract", "Celery task — extract_from_conversation"),
    ("src.workers.embed", "Celery task — embed_conversation"),
    ("src.api.routes.conversations", "Route: GET /conversations, GET /conversations/{id}"),
    ("src.api.routes.search", "Route: POST /search (pgvector semantic search)"),
    ("src.api.routes.topics", "Route: GET /topics, GET /topics/{id}"),
    ("src.api.routes.commitments", "Route: GET /commitments, PATCH /commitments/{id}"),
    ("src.api.routes.index_stats", "Route: GET /index/stats"),
    ("src.api.routes.calendar", "Route: GET /calendar/today"),
    ("src.models.conversation", "Model: Conversation"),
    ("src.models.transcript_segment", "Model: TranscriptSegment"),
    ("src.models.topic", "Model: Topic"),
    ("src.models.commitment", "Model: Commitment"),
    ("src.models.entity", "Model: Entity"),
    ("src.models.topic_arc", "Model: TopicArc"),
    ("src.models.connection", "Model: Connection"),
    ("src.models.brief", "Model: Brief"),
    ("src.models.index", "Model: Index"),
]

for mod, label in MODULES:
    try:
        importlib.import_module(mod)
        check(mod, label, True)
    except Exception as exc:
        check(mod, label, False, str(exc)[:200])


# ---------------------------------------------------------------------------
# 3. Database tables — all 9 tables exist in Supabase
# ---------------------------------------------------------------------------

section("3 · Database Tables (Supabase)")

EXPECTED_TABLES = [
    # Core tables (migration 001)
    "user_index",
    "conversations",
    "transcript_segments",
    "topics",
    "commitments",
    "entities",
    "topic_arcs",
    "connections",
    "briefs",
    # Junction tables (migration 002 — RLS enforced via user_id)
    "topic_segment_links",
    "commitment_segment_links",
    "entity_segment_links",
    "topic_arc_conversation_links",
    "brief_topic_arc_links",
    "brief_commitment_links",
    "brief_connection_links",
    "connection_linked_items",
]

_db_url = os.getenv("DATABASE_URL", "")
try:
    if not _db_url:
        raise RuntimeError("DATABASE_URL not set — skipping DB checks")
    conn = psycopg2.connect(_db_url, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    existing = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    for table in EXPECTED_TABLES:
        check(f"Table: {table}", f"Supabase table '{table}'", table in existing,
              "Table not found in database" if table not in existing else "")

except Exception as exc:
    for table in EXPECTED_TABLES:
        check(f"Table: {table}", f"Supabase table '{table}'", False, f"DB connection failed: {exc}")


# ---------------------------------------------------------------------------
# 4. RLS — row level security enforced on all user tables
# ---------------------------------------------------------------------------

section("4 · Row Level Security (RLS)")

try:
    if not _db_url:
        raise RuntimeError("DATABASE_URL not set — skipping RLS checks")
    conn = psycopg2.connect(_db_url, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        SELECT relname, relrowsecurity, relforcerowsecurity
        FROM pg_class
        WHERE relname = ANY(%s) AND relkind = 'r'
    """, (EXPECTED_TABLES,))
    rls_rows = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
    cur.close()
    conn.close()

    for table in EXPECTED_TABLES:
        if table not in rls_rows:
            check(f"RLS: {table}", f"RLS + FORCE on '{table}'", False, "Table not found")
        else:
            enabled, forced = rls_rows[table]
            ok = enabled and forced
            check(f"RLS: {table}", f"FORCE ROW LEVEL SECURITY on '{table}'", ok,
                  f"enabled={enabled} forced={forced} — must be both True" if not ok else "")

except Exception as exc:
    for table in EXPECTED_TABLES:
        check(f"RLS: {table}", f"RLS on '{table}'", False, f"DB connection failed: {exc}")


# ---------------------------------------------------------------------------
# 5. Unit tests
# ---------------------------------------------------------------------------

section("5 · Automated Unit Tests")

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "-m", "unit", "--tb=short", "-q"],
    capture_output=True, text=True, cwd=str(ROOT)
)
passed = result.returncode == 0
output = (result.stdout + result.stderr).strip()

# Count passed/failed from pytest output
lines = output.splitlines()
summary = next((l for l in reversed(lines) if "passed" in l or "failed" in l or "error" in l), output[-200:])
check("pytest unit suite", "All unit tests (no external services needed)", passed, "" if passed else summary)


# ---------------------------------------------------------------------------
# 6. Server health check — start uvicorn, hit /health, stop
# ---------------------------------------------------------------------------

section("6 · Server Health Check")

server_proc = None
try:
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--port", "18765", "--log-level", "error"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 8 seconds for the server to be ready
    ready = False
    for _ in range(16):
        time.sleep(0.5)
        try:
            r = httpx.get("http://localhost:18765/health", timeout=2)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass

    if ready:
        r = httpx.get("http://localhost:18765/health", timeout=5)
        check("GET /health → 200 OK", "Server starts and responds to health check", r.status_code == 200,
              f"Got status {r.status_code}" if r.status_code != 200 else "")
        check("Health response body", 'Returns {"status": "ok"}', r.json().get("status") == "ok",
              f"Got {r.text[:100]}")

        # Also hit /docs to confirm OpenAPI is live
        docs = httpx.get("http://localhost:18765/docs", timeout=5)
        check("GET /docs → 200 OK", "Interactive API docs page is live", docs.status_code == 200,
              f"Got status {docs.status_code}" if docs.status_code != 200 else "")
    else:
        check("GET /health → 200 OK", "Server starts and responds", False, "Server did not become ready in 8 seconds")

finally:
    if server_proc:
        server_proc.terminate()
        server_proc.wait()


# ---------------------------------------------------------------------------
# 7. LLM client — imports and Pydantic models are correct
# ---------------------------------------------------------------------------

section("7 · LLM Client Structure")

try:
    from src.llm_client import (
        CommitmentList,
        EntityList,
        TopicList,
        embed_texts,
        extract_commitments,
        extract_entities,
        extract_topics,
        generate_brief,
    )
    check("TopicList model", "Pydantic model for topic extraction", True)
    check("CommitmentList model", "Pydantic model for commitment extraction", True)
    check("EntityList model", "Pydantic model for entity extraction", True)
    check("extract_topics function", "Function is importable and callable", callable(extract_topics))
    check("extract_commitments function", "Function is importable and callable", callable(extract_commitments))
    check("extract_entities function", "Function is importable and callable", callable(extract_entities))
    check("generate_brief function", "Function is importable and callable", callable(generate_brief))
    check("embed_texts function", "OpenAI embedding function is importable and callable", callable(embed_texts))
except Exception as exc:
    check("LLM client imports", "All LLM client symbols importable", False, str(exc)[:200])


# ---------------------------------------------------------------------------
# 8. Celery tasks structure
# ---------------------------------------------------------------------------

section("8 · Celery Worker Tasks")

try:
    from src.workers.tasks import celery_app, generate_brief as gb_task, process_transcript
    from src.workers.extract import extract_from_conversation
    from src.workers.embed import embed_conversation
    check("Celery app", "Celery app instantiates without error", True)
    check("process_transcript task", "Task is importable", callable(process_transcript))
    check("generate_brief task", "Task is importable", callable(gb_task))
    check("extract_from_conversation task", "Wave 2 extraction task is importable", callable(extract_from_conversation))
    check("embed_conversation task", "Wave 2 embedding task is importable", callable(embed_conversation))
    registered = list(celery_app.tasks.keys())
    pt_registered = any("process_transcript" in t for t in registered)
    gb_registered = any("generate_brief" in t for t in registered)
    check("process_transcript registered", "Task appears in Celery task registry", pt_registered,
          "Not found in registry" if not pt_registered else "")
    check("generate_brief registered", "Task appears in Celery task registry", gb_registered,
          "Not found in registry" if not gb_registered else "")
except Exception as exc:
    check("Celery tasks", "Workers module loads", False, str(exc)[:200])


# ---------------------------------------------------------------------------
# Generate HTML report
# ---------------------------------------------------------------------------

total = len(results)
passed_count = sum(1 for r in results if r["passed"])
failed_count = total - passed_count
pct = int(passed_count / total * 100) if total else 0

overall_color = "#22c55e" if failed_count == 0 else ("#f59e0b" if pct >= 75 else "#ef4444")
overall_label = "All checks passed" if failed_count == 0 else f"{failed_count} check(s) need attention"

rows_html = ""
for r in results:
    icon = "✅" if r["passed"] else "❌"
    bg = "#f0fdf4" if r["passed"] else "#fef2f2"
    border = "#bbf7d0" if r["passed"] else "#fecaca"
    status_text = "PASS" if r["passed"] else "FAIL"
    status_color = "#16a34a" if r["passed"] else "#dc2626"
    info_html = f'<div class="info">{r["info"]}</div>' if r["info"] and not r["passed"] else ""
    rows_html += f"""
    <div class="check" style="background:{bg}; border-color:{border}">
      <div class="check-left">
        <span class="icon">{icon}</span>
        <div>
          <div class="check-name">{r["name"]}</div>
          <div class="check-detail">{r["detail"]}</div>
          {info_html}
        </div>
      </div>
      <span class="status" style="color:{status_color}">{status_text}</span>
    </div>"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pocket Nori QA Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f8fafc; color: #1e293b; padding: 32px 16px; }}
    .container {{ max-width: 780px; margin: 0 auto; }}
    h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }}
    .meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 28px; }}
    .summary {{ border-radius: 12px; padding: 24px 28px; margin-bottom: 28px;
                background: white; border: 2px solid {overall_color}; display: flex;
                align-items: center; gap: 20px; }}
    .score {{ font-size: 2.5rem; font-weight: 800; color: {overall_color}; }}
    .score-label {{ font-size: 1rem; font-weight: 600; color: {overall_color}; }}
    .score-sub {{ font-size: 0.875rem; color: #64748b; margin-top: 2px; }}
    .section-title {{ font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
                      letter-spacing: 0.08em; color: #94a3b8; margin: 20px 0 8px; }}
    .check {{ border: 1px solid; border-radius: 8px; padding: 12px 16px; margin-bottom: 6px;
              display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }}
    .check-left {{ display: flex; align-items: flex-start; gap: 12px; flex: 1; }}
    .icon {{ font-size: 1.1rem; margin-top: 1px; flex-shrink: 0; }}
    .check-name {{ font-weight: 600; font-size: 0.9rem; font-family: monospace; }}
    .check-detail {{ font-size: 0.8rem; color: #64748b; margin-top: 2px; }}
    .info {{ font-size: 0.78rem; color: #dc2626; margin-top: 4px; font-family: monospace; }}
    .status {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;
               white-space: nowrap; margin-top: 2px; }}
    .footer {{ margin-top: 28px; font-size: 0.8rem; color: #94a3b8; text-align: center; }}
  </style>
</head>
<body>
<div class="container">
  <h1>Pocket Nori — QA Report</h1>
  <div class="meta">Generated {datetime.now().strftime("%d %B %Y at %H:%M")}</div>

  <div class="summary">
    <div class="score">{pct}%</div>
    <div>
      <div class="score-label">{overall_label}</div>
      <div class="score-sub">{passed_count} of {total} checks passed</div>
    </div>
  </div>

  <div class="section-title">1 · Environment Variables</div>
  {''.join(rows_html.split('\n') and [r for r in rows_html.split('\n    <div class="check"') if 'SUPABASE_URL' in r or 'SUPABASE_ANON' in r or 'SUPABASE_SERVICE' in r or 'DATABASE_URL' in r or 'ANTHROPIC' in r or 'UPSTASH' in r or 'DEEPGRAM' in r or 'GOOGLE_CLIENT' in r or 'SECRET_KEY' in r]).join('<div class="check"') if False else ""}

  {rows_html}

  <div class="footer">Run again: <code>python scripts/qa_check.py</code></div>
</div>
</body>
</html>"""

# Simpler approach — just dump all rows grouped
sections_map = {
    "1 · Environment Variables": [r for r in results if any(v in r["name"] for v in ["SUPABASE", "ANTHROPIC", "UPSTASH", "DEEPGRAM", "GOOGLE", "SECRET", "DATABASE"])],
    "2 · Module Imports": [r for r in results if r["name"].startswith("src.")],
    "3 · Database Tables": [r for r in results if r["name"].startswith("Table:")],
    "4 · Row Level Security": [r for r in results if r["name"].startswith("RLS:")],
    "5 · Unit Tests": [r for r in results if "pytest" in r["name"]],
    "6 · Server Health": [r for r in results if "/health" in r["name"] or "/docs" in r["name"] or "Server" in r["name"]],
    "7 · LLM Client": [r for r in results if "model" in r["name"].lower() or "function" in r["name"].lower() or "LLM" in r["name"]],
    "8 · Celery Tasks": [r for r in results if "Celery" in r["name"] or "task" in r["name"].lower() or "registered" in r["name"]],
}

def make_row(r: dict) -> str:
    icon = "✅" if r["passed"] else "❌"
    bg = "#f0fdf4" if r["passed"] else "#fef2f2"
    border = "#bbf7d0" if r["passed"] else "#fecaca"
    status_text = "PASS" if r["passed"] else "FAIL"
    status_color = "#16a34a" if r["passed"] else "#dc2626"
    info_html = f'<div class="info">→ {r["info"]}</div>' if r["info"] and not r["passed"] else ""
    return f"""<div class="check" style="background:{bg}; border-color:{border}">
      <div class="check-left"><span class="icon">{icon}</span>
        <div><div class="check-name">{r["name"]}</div>
          <div class="check-detail">{r["detail"]}</div>{info_html}</div>
      </div>
      <span class="status" style="color:{status_color}">{status_text}</span>
    </div>"""

sections_html = ""
for sec_title, sec_results in sections_map.items():
    if not sec_results:
        continue
    sec_pass = sum(1 for r in sec_results if r["passed"])
    sec_total = len(sec_results)
    sec_color = "#16a34a" if sec_pass == sec_total else "#dc2626"
    sections_html += f'<div class="section-title">{sec_title} <span style="color:{sec_color};font-size:0.75rem">({sec_pass}/{sec_total})</span></div>\n'
    sections_html += "\n".join(make_row(r) for r in sec_results) + "\n"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pocket Nori QA Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f8fafc; color: #1e293b; padding: 32px 16px; }}
    .container {{ max-width: 820px; margin: 0 auto; }}
    h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }}
    .meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 28px; }}
    .summary {{ border-radius: 12px; padding: 24px 28px; margin-bottom: 32px;
                background: white; border: 2px solid {overall_color}; display: flex;
                align-items: center; gap: 24px; }}
    .score {{ font-size: 3rem; font-weight: 800; color: {overall_color}; line-height: 1; }}
    .score-label {{ font-size: 1.1rem; font-weight: 700; color: {overall_color}; }}
    .score-sub {{ font-size: 0.875rem; color: #64748b; margin-top: 4px; }}
    .section-title {{ font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
                      letter-spacing: 0.08em; color: #94a3b8; margin: 24px 0 8px; }}
    .check {{ border: 1px solid; border-radius: 8px; padding: 12px 16px; margin-bottom: 6px;
              display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }}
    .check-left {{ display: flex; align-items: flex-start; gap: 10px; flex: 1; min-width: 0; }}
    .icon {{ font-size: 1rem; margin-top: 2px; flex-shrink: 0; }}
    .check-name {{ font-weight: 600; font-size: 0.85rem; font-family: 'SF Mono', monospace; word-break: break-all; }}
    .check-detail {{ font-size: 0.78rem; color: #64748b; margin-top: 2px; }}
    .info {{ font-size: 0.75rem; color: #b91c1c; margin-top: 4px; font-family: monospace; word-break: break-all; }}
    .status {{ font-size: 0.7rem; font-weight: 800; letter-spacing: 0.06em;
               white-space: nowrap; padding-top: 3px; }}
    .footer {{ margin-top: 32px; font-size: 0.8rem; color: #94a3b8; text-align: center; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
  </style>
</head>
<body>
<div class="container">
  <h1>Pocket Nori — QA Report</h1>
  <div class="meta">Phase 0 Foundation · {datetime.now().strftime("%-d %B %Y, %H:%M")}</div>

  <div class="summary">
    <div class="score">{pct}%</div>
    <div>
      <div class="score-label">{overall_label}</div>
      <div class="score-sub">{passed_count} of {total} checks passed across 8 categories</div>
    </div>
  </div>

  {sections_html}

  <div class="footer">
    Run again any time: <code>source .venv/bin/activate &amp;&amp; python scripts/qa_check.py</code>
  </div>
</div>
</body>
</html>"""

REPORT_PATH.write_text(html, encoding="utf-8")

print(f"\n{'═' * 50}")
print(f"  QA complete: {passed_count}/{total} checks passed ({pct}%)")
print(f"  Report: {REPORT_PATH}")
print(f"{'═' * 50}\n")

webbrowser.open(f"file://{REPORT_PATH}")
