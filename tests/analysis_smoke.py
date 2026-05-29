"""Smoke test for the analysis endpoints.

Exercises upload + compliance fully. Brief generation only runs when
the server is on the Claude provider (Ollama brief is slow on iGPU
and not worth blocking CI on).

Usage:
    python tests/analysis_smoke.py [--with-brief]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

URL = "http://127.0.0.1:8765"
SAMPLE = Path(r"D:\Projects\TadqeeqAI\samples\sample_investment_fund_proposal.pdf")


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}", flush=True)
    if not condition:
        raise AssertionError(label)


def test_upload_and_metadata(c: httpx.Client) -> str:
    print("\n=== Upload + metadata ===")
    if not SAMPLE.exists():
        raise FileNotFoundError(f"Sample file not found: {SAMPLE}")
    with open(SAMPLE, "rb") as f:
        files = {"file": (SAMPLE.name, f, "application/pdf")}
        r = c.post(f"{URL}/api/analysis/documents", files=files, timeout=60)
    r.raise_for_status()
    meta = r.json()
    doc_id = meta["id"]
    _check("upload returns id", bool(doc_id), f"id={doc_id}")
    _check("filename echoed", meta["filename"] == SAMPLE.name)
    _check("page_count > 0", meta["page_count"] > 0, f"{meta['page_count']} pages")
    _check("char_count > 1000", meta["char_count"] > 1000, f"{meta['char_count']} chars")
    _check("summary attached", meta.get("summary") is not None)
    _check("summary.has_arabic present", "has_arabic" in (meta.get("summary") or {}))
    _check("has_compliance starts False", meta.get("has_compliance") is False)
    _check("has_brief starts False", meta.get("has_brief") is False)

    again = c.get(f"{URL}/api/analysis/documents/{doc_id}").json()
    _check("GET returns same id", again["id"] == doc_id)
    _check("GET excludes raw text", "text" not in again)
    return doc_id


def test_compliance(c: httpx.Client, doc_id: str) -> None:
    print("\n=== Compliance scan ===")
    r = c.post(f"{URL}/api/analysis/documents/{doc_id}/compliance",
               json={"strictness": "standard"}, timeout=15)
    r.raise_for_status()
    result = r.json()
    _check("6 checks returned", len(result["checks"]) == 6, f"got {len(result['checks'])}")
    _check("score is int 0..100", 0 <= result["score"] <= 100, f"score={result['score']}")
    _check("doc_language set", result["doc_language"] in ("en", "ar"))
    _check("summary.compliant + warnings = 6",
           result["summary"]["compliant"] + result["summary"]["warnings"] == 6)
    for chk in result["checks"]:
        _check(
            f"check {chk['id']} has both localizations",
            "en" in chk["localized"] and "ar" in chk["localized"],
        )

    cached = c.get(f"{URL}/api/analysis/documents/{doc_id}/compliance").json()
    _check("cached compliance matches", cached["score"] == result["score"])

    meta = c.get(f"{URL}/api/analysis/documents/{doc_id}").json()
    _check("has_compliance now True", meta["has_compliance"] is True)


def test_brief(c: httpx.Client, doc_id: str) -> None:
    print("\n=== Brief generation ===")
    print("  (running brief — this can take 60–180s on Ollama, 10–30s on Claude)", flush=True)
    r = c.post(f"{URL}/api/analysis/documents/{doc_id}/brief",
               json={"report_language": "auto"}, timeout=900)
    r.raise_for_status()
    result = r.json()
    _check("brief report non-empty", len(result["report"]) > 200, f"{len(result['report'])} chars")
    _check("primary language set", result["primary"] in ("en", "ar"))
    _check("localized has primary", result["primary"] in result["localized"])
    _check("language echo correct", result["language"] == "auto")

    meta = c.get(f"{URL}/api/analysis/documents/{doc_id}").json()
    _check("has_brief now True", meta["has_brief"] is True)


def test_list_and_delete(c: httpx.Client, doc_id: str) -> None:
    print("\n=== List + delete ===")
    listing = c.get(f"{URL}/api/analysis/documents").json()
    ids = [d["id"] for d in listing["documents"]]
    _check("our doc appears in list", doc_id in ids)
    r = c.delete(f"{URL}/api/analysis/documents/{doc_id}")
    _check("delete returns 204", r.status_code == 204)
    r = c.get(f"{URL}/api/analysis/documents/{doc_id}")
    _check("get after delete is 404", r.status_code == 404)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-brief", action="store_true",
                        help="Also test brief generation (slow on Ollama).")
    args = parser.parse_args()

    with httpx.Client(timeout=60) as c:
        health = c.get(f"{URL}/health").json()
        provider = health["llm_provider"]
        print(f"Server provider={provider!r} model={health['llm_model']!r}")

        doc_id = test_upload_and_metadata(c)
        test_compliance(c, doc_id)
        if args.with_brief or provider == "claude":
            test_brief(c, doc_id)
        else:
            print("\n=== Brief generation: SKIPPED (provider=ollama, no --with-brief flag) ===")
        test_list_and_delete(c, doc_id)
    print("\nAll analysis smoke checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        sys.exit(1)
