# Wayfinder

Per-project dashboard tool. Seven modules sit inside each project (Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode, Tech Stack, Deep Test), plus a top-level Interface that lists all projects.

## Kanban lifecycle

Four columns: **Building** (actively under construction, not yet usable), **Live** (built, in use, handoff-ready, only earned once a project has passed Deep Test, not just because it's technically running), **Parked** (deliberately set aside, not urgent, not stuck), **Blocked** (stuck on something external). There's no "Active" column, it never had a distinct meaning from Building. There's no "Brain Dump" column either: a project only enters the board once it has a repo (via the "unmapped GitHub repos" panel), and new projects already default to `status: Building` on creation.

## Stack

- Static site (`index.html`), no build step, deployed to GitHub Pages.
- Supabase Postgres (project `ueosmjwumqqyswmnbyji`), auto-generated REST endpoints called directly from the client with the anon key. No custom backend.

## Structure

- `index.html` — the Interface: Kanban/list/grid/gallery views of all projects, plus a per-project detail page with Session Log, Rubric, Build Diary, and Architecture Map panels. Architecture Map/Consideration Mode always render the real D3 force graph fetched from Supabase (CDN) — there's no hardcoded demo path in the code anymore.
- `assets/config.js` — Supabase URL and anon key used by the client.
- `supabase/schema.sql` — schema for `projects`, `rubric_lenses`, `diary_entries`, `session_log_entries`, `rubric_evolution_log`, `architecture_nodes`, `architecture_edges`, `architecture_snapshots`, `considerations`, `consideration_affected`, `github_repos`, `deep_test_items`, `deep_test_runs`, and `tech_stack_items` (RLS enabled, anon role granted full access since there's no auth layer).
- `scripts/import_architecture_graph.py` — one-off/rerunnable importer: runs `code-review-graph build` against a cloned project repo, reads its local SQLite graph, and loads File nodes plus resolved `IMPORTS_FROM` edges into Supabase for that project.
- `scripts/log_consideration.py` — computes the blast radius of a proposed change (BFS over the stored `IMPORTS_FROM` edges, reversed) and logs it as a Consideration for the dashboard to display.
- `scripts/sync_github_repos.py` — syncs the full GitHub repo list into `github_repos`, so the Interface can show which repos aren't a Wayfinder project yet.

## Main board is gated on analysis, not existence

The Kanban/List/Grid/Gallery board only queries and displays projects where `projects.analysis_status = 'complete'`. A `projects` row existing is not enough to earn a spot on the board — a project has to have actually been through Architecture Map analysis first. Everything else, regardless of why it isn't complete yet (never queued, queued, running, or failed), simply does not appear on the board in any view mode.

## Awaiting Analysis

Its own page, reached via the repo icon in the left rail (a badge on the icon shows the current combined count), not a panel bolted onto the board. It merges two categories into one flat list, with the same List/Grid/Gallery view-mode switcher as the main board:

1. **Existing projects not yet analysis-complete.** Every project row where `analysis_status` isn't `complete` lands here automatically, tagged "Awaiting analysis." This includes projects with no repo at all (GAS-bound scripts, Google Sheet systems) — they aren't exempt from the gate and don't get a special "N/A" treatment, they just wait here like anything else until an analyzer exists for non-repo tools (a separate future build item, not yet started).
2. **GitHub repos with no project row at all.** The original "unmapped repos" meaning, tagged "No repo yet." Clicking "+ Add to Wayfinder" on one (from any of the three views) creates a real `projects` row on the spot (id slugified from the repo name, goal pre-filled from the repo description if it has one, a default 4-lens rubric scaffold, `status: Building`, `venture: Unassigned`, `analysis_status: queued`), which immediately reclassifies it into category 1 above and opens straight to its new detail page. This only creates the metadata shell — Architecture Map/Consideration Mode still need a deliberate follow-up run (`import_architecture_graph.py`, then `log_consideration.py`) against that repo, same as Knowledge Loom Prismm.

A project moves from Awaiting Analysis onto the main board the moment `analysis_status` flips to `complete`, no separate step: both views query the same field, so running `import_architecture_graph.py` against a project is what actually promotes it.

### Analysis status

Since there's no custom backend, a dashboard click can never itself clone a repo and run the analysis — that only happens when a Claude session runs `import_architecture_graph.py`. Rather than a flat "pending" label, `projects.analysis_status` tracks real stages (`queued` → `running` → `complete`/`failed`), written by the script itself as it goes (`analysis_started_at` set when it starts). The dashboard shows this as a 3-segment stepper bar on the project's detail page — with an elapsed-time readout instead of a fabricated ETA, since actual duration depends on repo size and, for `queued`, on when a session next picks it up — plus a compact status pill on every board view. While a project's detail page is open with `queued`/`running` status, the dashboard polls Supabase every 5s and ticks the elapsed timer every 1s, so a run in progress is visible live; polling stops once status reaches `complete` or `failed`.

## Rubric

Four-lens pre-push gate per project (functional outcome, downstream surface effects, structural integrity, UX efficacy), plus a rubric-evolution log recording every change made to a lens. It's triggered on demand, not by automatic detection: say "run the rubric" during a Claude Code session on a project to have the current diff checked against that project's lenses.

## Architecture Map

Generated via [code-review-graph](https://github.com/tirth8205/code-review-graph), which parses a repo with Tree-sitter into a local SQLite graph of nodes and edges (12 edge kinds total: CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON, REFERENCES, INJECTS, CONSUMES, PRODUCES, TEMPORAL_STUB). Wayfinder imports only `File`/`Function`/`Class` nodes and resolved `IMPORTS_FROM` edges — that edge kind resolves reliably (internal file-to-file imports), whereas raw `CALLS` edges mostly point to unqualified names (React/hooks/npm calls, or false positives from non-JS files) and aren't reliable enough to key blast-radius logic off, so they're intentionally left out rather than building a fallback resolver for them.

Real runs so far: `keyona-rerev/knowledge-loom-prismm` (168 files, 580 nodes, 652 `IMPORTS_FROM` edges, 314 resolving internally) and `keyona-rerev/wayfinder` itself (5 files, 29 nodes, 31 edges — thin, since `code-review-graph` has no HTML parser and can't see anything inside `index.html`, only the standalone `.py`/`.sql` files). Bill Parser was never a real analysis target (client-critical infrastructure, never a build/test subject) and its demo project has since been removed from the board along with the other mockup-only entries (Athlete-Site.com, Super Connector CRM, BTC Comms Review) that never had a real Architecture Map — see "Unmapped GitHub repos" below for how projects get added now.

The dashboard renders the file-level import graph as a D3 force-directed layout (grouped/colored by top-level directory, pan/zoom, auto-fit once the simulation settles), fetched live from `architecture_nodes`/`architecture_edges` for whichever project has an `architecture_snapshots` row.

## Consideration Mode

Shows the blast radius of a proposed change by highlighting affected nodes on the Architecture Map: the changed file glows purple, everything that transitively imports it glows amber, everything else dims. Depends on Architecture Map already existing for a project.

Considerations are logged by Claude during a session, not authored from the dashboard — Keyona can only pick one from a dropdown, view it, and exit. `scripts/log_consideration.py --project-id <id> --file <path> --label "..."` walks the reversed `IMPORTS_FROM` graph already stored in Supabase from a changed file outward to find every direct and transitive importer, then writes a `considerations` row plus one `consideration_affected` row per affected file (each tagged with hop depth). The dashboard picks these up automatically the next time the Architecture Map panel is opened for that project.

## Tech Stack

A per-project list of every service it depends on (Supabase, Railway, Netlify, GitHub, whatever applies), each row a direct link to that specific resource's dashboard, not just the service's homepage. This is a fact about the project, not a workflow state, so it's always visible, no gate. An "Add tech stack item" form on the full page lets new entries get logged without a direct Supabase write. Both real projects are seeded with their actual Supabase/Netlify/GitHub links.

## Deep Test

Rubric is the per-change gate run during active building. Deep Test is a full pass over every essential function in a build, run at a milestone, to answer "is this actually handoff-ready," not "did this one push break anything." A project only earns `Live` status once it's passed Deep Test.

Each `deep_test_items` row pairs a function/behavior label with a specific test action and its expected outcome, plus a `pass`/`fail`/`untested` result. Where a project already has an Architecture Map, "Suggest items from Architecture Map" pre-fills candidates from `architecture_nodes` where the node kind is `Function` or `Class` (skipping any node already linked to an existing item via `source_node_id`), leaving `test_action`/`expected_outcome` blank for Keyona or a Claude session to fill in. Items can also always be added manually with no `source_node_id`, Architecture Map or not.

"Start Deep Test Run" creates a `deep_test_runs` row and switches the full page to a guided one-item-at-a-time view instead of a flat list to eyeball, since reducing cognitive load at the end of a long build is the whole point. Passing or failing an item advances to the next one not yet tested since the run started (computed from `last_tested_at` vs the run's `started_at`, so it resumes correctly even after a page reload); the run's `completed_at` gets set the moment none are left. A "Deep Test in progress" pill shows on the project's card in every board view (any Kanban column, not gated to a status) whenever a `deep_test_runs` row has `completed_at IS NULL`.

## Status

All seven modules (Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode, Tech Stack, Deep Test) plus the Interface are live against real Supabase data. The main board is gated on `analysis_status = 'complete'`, so it currently shows exactly two projects, Knowledge Loom Prismm and Wayfinder itself, both real Architecture Map runs. `projects` holds 34 rows total: those two, plus 32 migrated from Keyona's retired Tool Registry Google Sheet, all currently sitting in Awaiting Analysis until an Architecture Map run (or, for the roughly 18 with no repo, a future non-repo analyzer) completes for them.