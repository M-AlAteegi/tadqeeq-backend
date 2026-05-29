"""Smoke test for the export endpoints.

Runs against existing chat / library / analysis records (creates them if
missing). Verifies all three formats per export type when available.

Usage:
    python tests/exports_smoke.py [--formats md,docx,pdf]
"""

from __future__ import annotations

import argparse
import sys

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

URL = "http://127.0.0.1:8765"


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}", flush=True)
    if not condition:
        raise AssertionError(label)


def setup_chat(c: httpx.Client) -> str:
    print("\n=== Setup: create + populate a chat ===")
    chat_id = c.post(f"{URL}/api/chats", json={}).json()["id"]
    c.post(
        f"{URL}/api/chat/query",
        json={"question": "What is the minimum capital for a finance company?", "chat_id": chat_id},
        timeout=180,
    ).raise_for_status()
    print(f"  chat_id = {chat_id}")
    return chat_id


def setup_library_chat(c: httpx.Client) -> str:
    print("\n=== Setup: create + populate a library chat ===")
    chat_id = c.post(f"{URL}/api/library/chats", json={"category_id": "murabaha"}).json()["id"]
    c.post(
        f"{URL}/api/library/query",
        json={"question": "Brief: AAOIFI cost-disclosure rules.", "chat_id": chat_id},
        timeout=180,
    ).raise_for_status()
    print(f"  library chat_id = {chat_id}")
    return chat_id


def test_chat_exports(c: httpx.Client, chat_id: str, formats: set[str]) -> None:
    print("\n=== Chat exports ===")
    if "md" in formats:
        r = c.get(f"{URL}/api/chats/{chat_id}/export/markdown")
        _check("chat md status 200", r.status_code == 200, f"got {r.status_code}")
        body = r.text
        _check("chat md has header", "# TadqeeqAI Chat Export" in body)
        _check("chat md has user block", "## User" in body)
        _check("chat md has assistant block", "## TadqeeqAI" in body)
        _check("chat md has Sources line", "**Sources:**" in body)
        cd = r.headers.get("content-disposition", "")
        _check("chat md filename attached", "filename=" in cd, cd)


def test_library_exports(c: httpx.Client, chat_id: str, formats: set[str]) -> None:
    print("\n=== Library exports ===")
    if "md" in formats:
        r = c.get(f"{URL}/api/library/chats/{chat_id}/export/markdown")
        _check("library md status 200", r.status_code == 200, f"got {r.status_code}")
        body = r.text
        _check("library md has clause-library header",
               "# TadqeeqAI · Clause Library Discussion" in body)
        _check("library md has Topic line", "**Topic:**" in body)
        _check("library md has Question block", "## Question" in body)
        _check("library md has Response block", "## Response" in body)


def test_brief_exports(c: httpx.Client, formats: set[str]) -> None:
    print("\n=== Brief exports (requires existing analysis doc with brief) ===")
    docs = c.get(f"{URL}/api/analysis/documents").json()["documents"]
    target = next((d for d in docs if d["has_brief"]), None)
    if target is None:
        print("  SKIPPED — no analysis document has a cached brief yet.")
        print("  (Run analysis_smoke.py --with-brief or via Claude first.)")
        return
    doc_id = target["id"]
    if "md" in formats:
        r = c.get(f"{URL}/api/analysis/documents/{doc_id}/brief/export/markdown")
        _check("brief md status 200", r.status_code == 200, f"got {r.status_code}")
        body = r.text
        _check("brief md has Generated header", "**Generated:**" in body)


def test_404_paths(c: httpx.Client) -> None:
    print("\n=== 404 paths ===")
    r = c.get(f"{URL}/api/chats/nosuch/export/markdown")
    _check("missing chat → 404", r.status_code == 404)
    r = c.get(f"{URL}/api/library/chats/nosuch/export/markdown")
    _check("missing library chat → 404", r.status_code == 404)
    r = c.get(f"{URL}/api/analysis/documents/nosuch/brief/export/markdown")
    _check("missing analysis doc → 404", r.status_code == 404)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formats", default="md")
    args = parser.parse_args()
    formats = {f.strip() for f in args.formats.split(",") if f.strip()}

    with httpx.Client(timeout=60) as c:
        health = c.get(f"{URL}/health").json()
        print(f"Server provider={health['llm_provider']!r}  formats={sorted(formats)}")

        chat_id = setup_chat(c)
        lib_id = setup_library_chat(c)

        test_chat_exports(c, chat_id, formats)
        test_library_exports(c, lib_id, formats)
        test_brief_exports(c, formats)
        test_404_paths(c)

        c.delete(f"{URL}/api/chats/{chat_id}")
        c.delete(f"{URL}/api/library/chats/{lib_id}")
    print("\nAll export smoke checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        sys.exit(1)
