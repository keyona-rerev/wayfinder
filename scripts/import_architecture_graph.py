#!/usr/bin/env python3
"""Import a code-review-graph SQLite graph into Wayfinder's Supabase tables.

Usage:
    pip install code-review-graph
    cd /path/to/target-repo && code-review-graph build
    python3 scripts/import_architecture_graph.py --repo /path/to/target-repo --project-id knowledge-loom

Only File/Function/Class nodes and resolved IMPORTS_FROM edges are imported.
Raw CALLS edges mostly resolve to unqualified names (React/hooks/npm calls),
not a specific file+function, so they're intentionally left out rather than
building a fallback resolver for them. Re-running this script fully replaces
the prior graph for the given project id.
"""
import argparse
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


def load_config():
    config_path = Path(__file__).resolve().parent.parent / "assets" / "config.js"
    text = config_path.read_text()
    url = re.search(r"SUPABASE_URL:\s*'([^']+)'", text).group(1)
    key = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", text).group(1)
    return url, key


def rest_request(base_url, key, method, path, body=None, extra_headers=None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base_url}/rest/v1/{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def normalize(value, repo_root):
    prefix = repo_root.rstrip("/") + "/"
    return value[len(prefix):] if value.startswith(prefix) else value


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="Path to the cloned target repo (must already have run `code-review-graph build`)")
    parser.add_argument("--project-id", required=True, help="Wayfinder project id (matches projects.id)")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    repo_root = str(Path(args.repo).resolve())
    db_path = Path(repo_root) / ".code-review-graph" / "graph.db"
    if not db_path.exists():
        raise SystemExit(f"No graph.db found at {db_path}. Run `code-review-graph build` in {repo_root} first.")

    supabase_url, supabase_key = load_config()

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute("select kind, name, qualified_name, file_path, line_start, line_end, language, parent_name from nodes")
    raw_nodes = cur.fetchall()
    cur.execute("select source_qualified, target_qualified, file_path, line from edges where kind='IMPORTS_FROM'")
    raw_edges = cur.fetchall()

    node_rows = []
    qnames = set()
    for kind, name, qn, fp, line_start, line_end, language, parent_name in raw_nodes:
        nqn = normalize(qn, repo_root)
        nname = normalize(name, repo_root) if kind == "File" else name
        nfp = normalize(fp, repo_root)
        qnames.add(nqn)
        node_rows.append({
            "project_id": args.project_id, "kind": kind, "name": nname, "qualified_name": nqn,
            "file_path": nfp, "line_start": line_start, "line_end": line_end,
            "language": language, "parent_name": parent_name,
        })

    edge_rows = []
    for sq, tq, fp, line in raw_edges:
        nsq, ntq, nfp = normalize(sq, repo_root), normalize(tq, repo_root), normalize(fp, repo_root)
        edge_rows.append({
            "project_id": args.project_id, "kind": "IMPORTS_FROM", "source_qualified": nsq,
            "target_qualified": ntq, "file_path": nfp, "line": line, "resolved": ntq in qnames,
        })

    files_parsed = sum(1 for n in node_rows if n["kind"] == "File")

    # Full replace for this project on every run.
    rest_request(supabase_url, supabase_key, "DELETE", f"architecture_nodes?project_id=eq.{args.project_id}")
    rest_request(supabase_url, supabase_key, "DELETE", f"architecture_edges?project_id=eq.{args.project_id}")

    for i in range(0, len(node_rows), args.batch_size):
        rest_request(supabase_url, supabase_key, "POST", "architecture_nodes", node_rows[i:i + args.batch_size])
    for i in range(0, len(edge_rows), args.batch_size):
        rest_request(supabase_url, supabase_key, "POST", "architecture_edges", edge_rows[i:i + args.batch_size])

    rest_request(
        supabase_url, supabase_key, "POST", "architecture_snapshots",
        {"project_id": args.project_id, "files_parsed": files_parsed, "node_count": len(node_rows), "edge_count": len(edge_rows)},
        extra_headers={"Prefer": "resolution=merge-duplicates"},
    )

    print(f"Imported {len(node_rows)} nodes, {len(edge_rows)} edges ({files_parsed} files) for project '{args.project_id}'.")


if __name__ == "__main__":
    main()
