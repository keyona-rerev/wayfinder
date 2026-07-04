# Wayfinder

Per-project dashboard tool. Five modules sit inside each project (Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode), plus a top-level Interface that lists all projects.

## Stack

- Static site (`index.html`), no build step, deployed to GitHub Pages.
- Supabase Postgres (project `ueosmjwumqqyswmnbyji`), auto-generated REST endpoints called directly from the client with the anon key. No custom backend.

## Structure

- `index.html` — the Interface: Kanban/list/grid/gallery views of all projects, plus a per-project detail page with Session Log, Rubric, Build Diary, and Architecture Map panels (including the Consideration Mode demo, seeded on Bill Parser data). Uses D3 (CDN) for the real Architecture Map force graph.
- `assets/config.js` — Supabase URL and anon key used by the client.
- `supabase/schema.sql` — schema for `projects`, `rubric_lenses`, `diary_entries`, `session_log_entries`, `rubric_evolution_log`, `architecture_nodes`, `architecture_edges`, `architecture_snapshots`, `considerations`, and `consideration_affected` (RLS enabled, anon role granted full access since there's no auth layer).
- `scripts/import_architecture_graph.py` — one-off/rerunnable importer: runs `code-review-graph build` against a cloned project repo, reads its local SQLite graph, and loads File nodes plus resolved `IMPORTS_FROM` edges into Supabase for that project.
- `scripts/log_consideration.py` — computes the blast radius of a proposed change (BFS over the stored `IMPORTS_FROM` edges, reversed) and logs it as a Consideration for the dashboard to display.
- `scripts/sync_github_repos.py` — syncs the full GitHub repo list into `github_repos`, so the Interface can show which repos aren't a Wayfinder project yet.

## Unmapped GitHub repos

Below the main board, a collapsible "unmapped GitHub repos" panel lists every synced repo (`github_repos`) that no `projects` row points to via `repo_full_name`. Clicking "+ Add to Wayfinder" on one creates a real `projects` row on the spot (id slugified from the repo name, goal pre-filled from the repo description if it has one, a default 4-lens rubric scaffold, `status: Building`, `venture: Unassigned`) so it shows up on the board immediately. This only creates the metadata shell — Architecture Map/Consideration Mode still need a deliberate follow-up run (`import_architecture_graph.py`, then `log_consideration.py`) against that repo, same as Knowledge Loom Prismm.

## Rubric

Four-lens pre-push gate per project (functional outcome, downstream surface effects, structural integrity, UX efficacy), plus a rubric-evolution log recording every change made to a lens. It's triggered on demand, not by automatic detection: say "run the rubric" during a Claude Code session on a project to have the current diff checked against that project's lenses.

## Architecture Map

Generated via [code-review-graph](https://github.com/tirth8205/code-review-graph), which parses a repo with Tree-sitter into a local SQLite graph of nodes and edges (12 edge kinds total: CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON, REFERENCES, INJECTS, CONSUMES, PRODUCES, TEMPORAL_STUB). Wayfinder imports only `File`/`Function`/`Class` nodes and resolved `IMPORTS_FROM` edges — that edge kind resolves reliably (internal file-to-file imports), whereas raw `CALLS` edges mostly point to unqualified names (React/hooks/npm calls, or false positives from non-JS files) and aren't reliable enough to key blast-radius logic off, so they're intentionally left out rather than building a fallback resolver for them.

First real project run: `keyona-rerev/knowledge-loom-prismm` — 168 files parsed, 580 nodes (168 File, 396 Function, 16 Class), 652 `IMPORTS_FROM` edges (314 resolving to internal files, the rest to external packages). Bill Parser keeps its small hand-authored demo graph instead of a real one, since Bill Parser is client-critical infrastructure that's never a build/test subject.

The dashboard renders the file-level import graph as a D3 force-directed layout (grouped/colored by top-level directory, pan/zoom, auto-fit once the simulation settles), fetched live from `architecture_nodes`/`architecture_edges` for whichever project has an `architecture_snapshots` row.

## Consideration Mode

Shows the blast radius of a proposed change by highlighting affected nodes on the Architecture Map: the changed file glows purple, everything that transitively imports it glows amber, everything else dims. Depends on Architecture Map already existing for a project.

Considerations are logged by Claude during a session, not authored from the dashboard — Keyona can only pick one from a dropdown, view it, and exit, the same restriction the original Bill Parser demo models. `scripts/log_consideration.py --project-id <id> --file <path> --label "..."` walks the reversed `IMPORTS_FROM` graph already stored in Supabase from a changed file outward to find every direct and transitive importer, then writes a `considerations` row plus one `consideration_affected` row per affected file (each tagged with hop depth). The dashboard picks these up automatically the next time the Architecture Map panel is opened for that project.

## Status

All five modules (Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode) plus the Interface are live against real Supabase data.