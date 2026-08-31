#!/usr/bin/env python3
"""Move a Pulse Delivery card to the phase implied by a GitHub PR event.

GitHub is the source of truth; this pushes the derived phases (5, 6, 7, 8) into
Notion so nothing is maintained twice. Phases 2, 3, 4 and 10 are not visible to
GitHub and stay agent/human-driven.

The card is found by the FEAT-nn id in the PR title or head branch. No id means
nothing to do — this script must never fail a pull request.

Env:
  NOTION_TOKEN        internal integration secret (required)
  NOTION_DATABASE_ID  the Pulse Delivery database (required)
  GH_EVENT            pull_request | pull_request_review
  GH_ACTION           opened | reopened | ready_for_review | review_requested | closed | submitted
  GH_MERGED           true|false (pull_request.closed only)
  GH_REVIEW_STATE     approved | changes_requested | commented
  GH_PR_TITLE, GH_PR_BRANCH, GH_PR_URL
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"

DEV = "5 · Development"
REVIEW = "6 · Review"
VERIFY = "7 · Verification"
DEPLOY = "8 · Deployment"


def env(name, default=""):
    return os.environ.get(name, default) or default


def call(method, path, payload=None):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {env('NOTION_TOKEN')}",
            "Notion-Version": VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        sys.exit(f"Notion API {exc.code} on {method} {path}: {body}")


def target_phase():
    """The phase this event implies, or None to leave the card alone."""
    event, action = env("GH_EVENT"), env("GH_ACTION")

    if event == "pull_request_review" and action == "submitted":
        state = env("GH_REVIEW_STATE").lower()
        if state == "approved":
            return VERIFY
        if state == "changes_requested":
            return DEV  # the loop working: review sends it back
        return None  # a plain comment is not a transition

    if event == "pull_request":
        if action in ("opened", "reopened"):
            return DEV
        if action in ("ready_for_review", "review_requested"):
            return REVIEW
        if action == "closed":
            return DEPLOY if env("GH_MERGED") == "true" else None

    return None


def find_card(feat_id):
    """Scan the database for the card whose unique id matches. Small board, one pass."""
    cursor, payload = None, {"page_size": 100}
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        data = call("POST", f"/databases/{env('NOTION_DATABASE_ID')}/query", payload)
        for page in data.get("results", []):
            prop = page.get("properties", {}).get("ID", {})
            if prop.get("type") == "unique_id":
                if prop["unique_id"].get("number") == feat_id:
                    return page
        if not data.get("has_more"):
            return None
        cursor = data["next_cursor"]


def main():
    phase = target_phase()
    if phase is None:
        print(f"No phase change for {env('GH_EVENT')}/{env('GH_ACTION')} — nothing to do.")
        return

    match = re.search(r"FEAT-(\d+)", f"{env('GH_PR_TITLE')} {env('GH_PR_BRANCH')}", re.I)
    if not match:
        print("No FEAT-nn in the PR title or branch — skipping. Name the branch feat/FEAT-12-slug.")
        return
    feat_id = int(match.group(1))

    card = find_card(feat_id)
    if card is None:
        print(f"FEAT-{feat_id} has no card on the board — skipping.")
        return

    props = {"Phase": {"select": {"name": phase}}}
    if env("GH_PR_URL"):
        props["GitHub PR"] = {"url": env("GH_PR_URL")}

    # A bounce back to development is a repair cycle. Cap at 3, then flag it.
    if phase == DEV and env("GH_REVIEW_STATE").lower() == "changes_requested":
        current = card["properties"].get("Repair attempts", {}).get("number") or 0
        attempts = int(current) + 1
        props["Repair attempts"] = {"number": attempts}
        if attempts >= 3:
            props["Blocked"] = {"checkbox": True}
            print(f"FEAT-{feat_id} hit {attempts} repair cycles — marked Blocked for a human.")

    call("PATCH", f"/pages/{card['id']}", {"properties": props})
    print(f"FEAT-{feat_id} → {phase}")


if __name__ == "__main__":
    main()
