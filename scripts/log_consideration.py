#!/usr/bin/env python3
"""Log a Consideration Mode run: compute the blast radius of a proposed change
from the IMPORTS_FROM edges already stored in Supabase for a project, and
persist it so the dashboard can show it.

Meant to be run by Claude during a coding session on the target project, not
by hand from the dashboard: Keyona can only view and exit considerations
there, never author them directly (same pattern as the Bill Parser demo).

Usage:
    python3 scripts/log_consideration.py --project-id knowledge-loom \\
        --file src/lib/scheduleResolver.ts --label "Change date parsing logic"

--file must match an architecture_nodes.qualified_name for that project
(a repo-relative file path, as imported by import_architecture_graph.py).
"""
import argparse
import json
import re
import time
import urllib.request
from collections import deque
from pathlib import Path


def load_config():
    config_path = Path(__file__).resolve().parent.parent / "assets" / "config.js"
    text = config_path.read_text()
    url = re.search(r"SUPABASE_URL:\s*'([^']+)'", text).group(1)
    key = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", text).group(1)
    return url, key


def rest_get(base_url, key, path):
    req = urllib.request.Request(f"{base_url}/rest/v1/{path}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def rest_post(base_url, key, path, body, extra_headers=None):
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(f"{base_url}/rest/v1/{path}", data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def slugify(label):
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "consideration"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--file", required=True, help="Repo-relative path of the file being changed")
    parser.add_argument("--label", required=True, help="Short description of the proposed change")
    args = parser.parse_args()

    supabase_url, supabase_key = load_config()

    edges = rest_get(
        supabase_url, supabase_key,
        f"architecture_edges?project_id=eq.{args.project_id}&kind=eq.IMPORTS_FROM&resolved=eq.true&select=source_qualified,target_qualified",
    )

    # Reverse-import graph: target -> [files that import it].
    importers = {}
    for e in edges:
        importers.setdefault(e["target_qualified"], []).append(e["source_qualified"])

    # BFS outward from the changed file to find everything that (transitively) imports it.
    visited = {args.file: 0}
    queue = deque([args.file])
    while queue:
        current = queue.popleft()
        for importer in importers.get(current, []):
            if importer not in visited:
                visited[importer] = visited[current] + 1
                queue.append(importer)

    affected = sorted(((qn, depth) for qn, depth in visited.items() if qn != args.file), key=lambda x: x[1])

    if not affected:
        print(f"No importers found for {args.file} in project '{args.project_id}' — nothing to log.")
        return

    consideration_id = f"{slugify(args.label)}-{int(time.time())}"

    rest_post(supabase_url, supabase_key, "considerations", {
        "id": consideration_id, "project_id": args.project_id, "label": args.label, "source_qualified": args.file,
    })

    affected_rows = [
        {
            "consideration_id": consideration_id,
            "target_qualified": qn,
            "note": f"Imports {args.file} directly." if depth == 1 else f"Transitively depends on {args.file} ({depth} hops away).",
            "depth": depth,
        }
        for qn, depth in affected
    ]
    rest_post(supabase_url, supabase_key, "consideration_affected", affected_rows)

    print(f"Logged consideration '{consideration_id}': {len(affected_rows)} affected files.")


if __name__ == "__main__":
    main()
