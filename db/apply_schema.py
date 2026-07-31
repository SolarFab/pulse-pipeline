#!/usr/bin/env python3
"""
Apply the Supabase schema via the Management API.
Run from the event-map directory:
    python db/apply_schema.py
"""

import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Extract project ref from URL: https://xxxx.supabase.co -> xxxx
project_ref = SUPABASE_URL.replace("https://", "").split(".")[0]

with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
    schema = f.read()

# Remove pure comment lines and split on semicolons
statements = []
for stmt in re.split(r";\s*\n", schema):
    stmt = stmt.strip()
    # Skip empty or comment-only blocks
    lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")]
    if lines:
        statements.append(stmt)

print(f"Applying {len(statements)} SQL statements to project {project_ref}...")

headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}

errors = []
for i, stmt in enumerate(statements):
    label = stmt[:60].replace("\n", " ")
    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
            json={"query": stmt + ";"},
            headers=headers,
            timeout=30,
        )
        if resp.status_code in (200, 201, 204):
            print(f"  ✓ [{i + 1}/{len(statements)}] {label}")
        else:
            # Some statements (CREATE EXTENSION, CREATE INDEX IF NOT EXISTS) return errors
            # if already applied — that's fine
            body = resp.text[:200]
            if "already exists" in body or "duplicate" in body.lower():
                print(f"  ~ [{i + 1}/{len(statements)}] Already exists: {label}")
            else:
                print(f"  ✗ [{i + 1}/{len(statements)}] {resp.status_code}: {body}")
                errors.append((stmt, resp.text))
    except Exception as e:
        print(f"  ✗ [{i + 1}/{len(statements)}] Exception: {e}")
        errors.append((stmt, str(e)))

if errors:
    print(f"\n{len(errors)} errors. The exec_sql RPC may not be available.")
    print("Please apply the schema manually:")
    print("  1. Go to https://supabase.com/dashboard/project/{project_ref}/sql")
    print("  2. Paste db/schema.sql and click Run")
else:
    print("\n✓ Schema applied successfully")
