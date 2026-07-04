#!/usr/bin/env python3
"""Sync GitHub repos into Wayfinder's github_repos table, for the Interface's
"unmapped repos" list.

Meant to be re-run periodically (by Claude, using whatever GitHub access is
available in a given session, or by hand with a personal access token) to
pick up new/renamed/deleted repos. Existing rows are upserted by full_name;
nothing is ever deleted automatically, since a repo temporarily missing from
one page of results shouldn't silently vanish from the list.

Usage:
    GITHUB_TOKEN=ghp_... python3 scripts/sync_github_repos.py [--owner keyona-rerev]
"""
import argparse
import json
import os
import re
import urllib.request
from pathlib import Path


def load_config():
    config_path = Path(__file__).resolve().parent.parent / "assets" / "config.js"
    text = config_path.read_text()
    url = re.search(r"SUPABASE_URL:\s*'([^']+)'", text).group(1)
    key = re.search(r"SUPABASE_ANON_KEY:\s*'([^']+)'", text).group(1)
    return url, key


def rest_post(base_url, key, path, body, extra_headers=None):
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(f"{base_url}/rest/v1/{path}", data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def fetch_all_repos(token, owner_type):
    repos = []
    page = 1
    while True:
        req = urllib.request.Request(
            f"https://api.github.com/user/repos?per_page=100&page={page}&sort=pushed&type={owner_type}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--owner-type", default="owner", choices=["all", "owner", "public", "private", "member"])
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN to a GitHub personal access token before running this.")

    supabase_url, supabase_key = load_config()
    repos = fetch_all_repos(token, args.owner_type)

    rows = [
        {
            "full_name": r["full_name"],
            "name": r["name"],
            "owner": r["owner"]["login"],
            "description": r.get("description"),
            "private": r["private"],
            "language": r.get("language"),
            "html_url": r["html_url"],
            "default_branch": r.get("default_branch", "main"),
            "pushed_at": r.get("pushed_at"),
        }
        for r in repos
    ]

    for i in range(0, len(rows), 100):
        rest_post(
            supabase_url, supabase_key, "github_repos?on_conflict=full_name", rows[i:i + 100],
            extra_headers={"Prefer": "resolution=merge-duplicates"},
        )

    print(f"Synced {len(rows)} repos into github_repos.")


if __name__ == "__main__":
    main()
