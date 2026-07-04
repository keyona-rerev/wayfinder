# Wayfinder

Per-project dashboard tool. Five modules sit inside each project (Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode), plus a top-level Interface that lists all projects.

## Stack

- Static site (`index.html`), no build step, deployed to GitHub Pages.
- Supabase Postgres (project `ueosmjwumqqyswmnbyji`), auto-generated REST endpoints called directly from the client with the anon key. No custom backend.

## Structure

- `index.html` — the Interface: Kanban/list/grid/gallery views of all projects, plus a per-project detail page with Rubric, Build Diary, and Architecture Map panels (including the Consideration Mode demo, seeded on Bill Parser data).
- `assets/config.js` — Supabase URL and anon key used by the client.
- `supabase/schema.sql` — schema for the `projects`, `rubric_lenses`, and `diary_entries` tables (RLS enabled, anon role granted full access since there's no auth layer).

## Status

Interface is live against real Supabase data. Remaining modules build out in order: Session Log, Build Diary, Rubric, Architecture Map, Consideration Mode.