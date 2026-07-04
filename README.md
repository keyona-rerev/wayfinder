# Wayfinder

Per-project dashboard tool. Five modules sit inside each project (Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode), plus a top-level Interface that lists all projects.

## Stack

- Static site (`index.html`), no build step, deployed to GitHub Pages.
- Supabase Postgres (project `ueosmjwumqqyswmnbyji`), auto-generated REST endpoints called directly from the client with the anon key. No custom backend.

## Structure

- `index.html` — the Interface: Kanban/list/grid/gallery views of all projects, plus a per-project detail page with Session Log, Rubric, Build Diary, and Architecture Map panels (including the Consideration Mode demo, seeded on Bill Parser data).
- `assets/config.js` — Supabase URL and anon key used by the client.
- `supabase/schema.sql` — schema for `projects`, `rubric_lenses`, `diary_entries`, `session_log_entries`, and `rubric_evolution_log` (RLS enabled, anon role granted full access since there's no auth layer).

## Rubric

Four-lens pre-push gate per project (functional outcome, downstream surface effects, structural integrity, UX efficacy), plus a rubric-evolution log recording every change made to a lens. It's triggered on demand, not by automatic detection: say "run the rubric" during a Claude Code session on a project to have the current diff checked against that project's lenses.

## Status

Interface, Session Log, Build Diary, and Rubric are live against real Supabase data. Remaining modules build out in order: Architecture Map, Consideration Mode.