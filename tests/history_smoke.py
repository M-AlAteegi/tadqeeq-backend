"""Smoke test for the history endpoints + persistence wiring.

Verifies:
  - POST /api/chats creates a chat with empty messages
  - POST /api/chat/query with chat_id appends user + assistant messages
  - GET  /api/chats lists the chat with regulator field populated
  - GET  /api/chats/{id} returns the full chat with sources stored
  - DELETE /api/chats/{id} removes it
  - Same flow for /api/library/chats (with category_id)
  - SSE library stream emits chat event first when create_chat=True
"""

from __future__ import annotations

import json
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


def test_regular_chat(c: httpx.Client) -> None:
    print("\n=== Regular chat lifecycle ===")
    r = c.post(f"{URL}/api/chats", json={})
    r.raise_for_status()
    chat_id = r.json()["id"]
    _check("create returns id", bool(chat_id), f"id={chat_id}")

    detail = c.get(f"{URL}/api/chats/{chat_id}").json()
    _check("fresh chat has 0 messages", len(detail["messages"]) == 0)

    payload = {"question": "What is the minimum capital for a finance company?", "chat_id": chat_id}
    r = c.post(f"{URL}/api/chat/query", json=payload, timeout=180)
    r.raise_for_status()
    body = r.json()
    _check("query returns answer", len(body["answer"]) > 20)
    _check("query returns SAMA regulator", body["regulator"] == "SAMA", body["regulator"])

    detail = c.get(f"{URL}/api/chats/{chat_id}").json()
    _check("chat now has 2 messages", len(detail["messages"]) == 2, f"got {len(detail['messages'])}")
    _check("user message role correct", detail["messages"][0]["role"] == "user")
    _check("assistant message role correct", detail["messages"][1]["role"] == "assistant")
    _check("assistant has sources", len(detail["messages"][1].get("sources", [])) > 0)
    _check("assistant has regulator", detail["messages"][1].get("regulator") == "SAMA")

    listing = c.get(f"{URL}/api/chats").json()["chats"]
    found = next((x for x in listing if x["id"] == chat_id), None)
    _check("chat appears in list", found is not None)
    _check("list summary regulator==SAMA", found and found.get("regulator") == "SAMA")
    _check("list summary message_count==2", found and found.get("message_count") == 2)

    r = c.delete(f"{URL}/api/chats/{chat_id}")
    _check("delete returns 204", r.status_code == 204)
    r = c.get(f"{URL}/api/chats/{chat_id}")
    _check("get after delete is 404", r.status_code == 404)


def test_library_chat(c: httpx.Client) -> None:
    print("\n=== Library chat lifecycle ===")
    r = c.post(f"{URL}/api/library/chats", json={"category_id": "murabaha"})
    r.raise_for_status()
    chat_id = r.json()["id"]
    _check("create returns id", bool(chat_id), f"id={chat_id}")

    detail = c.get(f"{URL}/api/library/chats/{chat_id}").json()
    _check("category_id stored", detail.get("category_id") == "murabaha")

    payload = {"question": "Brief: AAOIFI cost-disclosure rules.", "chat_id": chat_id}
    r = c.post(f"{URL}/api/library/query", json=payload, timeout=180)
    r.raise_for_status()
    body = r.json()
    _check("library query returns answer", len(body["answer"]) > 20)
    _check("library query echoes chat_id", body["chat_id"] == chat_id)

    detail = c.get(f"{URL}/api/library/chats/{chat_id}").json()
    _check("library chat has 2 messages", len(detail["messages"]) == 2)

    listing = c.get(f"{URL}/api/library/chats").json()["chats"]
    found = next((x for x in listing if x["id"] == chat_id), None)
    _check("library chat appears in list", found is not None)
    _check("list summary category_id==murabaha", found and found.get("category_id") == "murabaha")

    r = c.delete(f"{URL}/api/library/chats/{chat_id}")
    _check("delete returns 204", r.status_code == 204)


def test_streaming_persistence(c: httpx.Client) -> None:
    print("\n=== SSE persistence (library stream with create_chat) ===")
    chat_id_from_event: str | None = None
    token_events = 0
    payload = {"question": "What is a sukuk?", "create_chat": True, "category_id": "sukuk"}
    with c.stream("POST", f"{URL}/api/library/query/stream", json=payload, timeout=180) as r:
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:].strip())
            if ev["type"] == "chat":
                chat_id_from_event = ev["chat_id"]
            elif ev["type"] == "token":
                token_events += 1
    _check("stream emitted chat event first", bool(chat_id_from_event))
    _check("stream emitted token events", token_events > 0, f"got {token_events}")

    detail = c.get(f"{URL}/api/library/chats/{chat_id_from_event}").json()
    _check("persisted user + assistant", len(detail["messages"]) == 2)
    assistant_len = len(detail["messages"][1]["content"])
    _check("assistant content non-empty", assistant_len > 50, f"len={assistant_len}")
    c.delete(f"{URL}/api/library/chats/{chat_id_from_event}")


def main() -> int:
    with httpx.Client(timeout=60) as c:
        health = c.get(f"{URL}/health").json()
        print(f"Server provider={health['llm_provider']!r} model={health['llm_model']!r}")
        test_regular_chat(c)
        test_library_chat(c)
        test_streaming_persistence(c)
    print("\nAll history smoke checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        sys.exit(1)
