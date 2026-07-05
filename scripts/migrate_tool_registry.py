#!/usr/bin/env python3
"""One-off migration: retire Keyona's Tool Registry Google Sheet
(1ol8Yvpe454T4yHpEgy8PFjOAJvfyUDrKesgD_wM7m4o, tab "Registry") and bring
every one of its 32 rows into Wayfinder as a full project.

The Registry is being retired by this migration, so its 32 rows are
embedded below exactly as read from the sheet on the migration date via
the Google Sheets MCP connector, rather than re-fetched live on every
run. This also keeps the script a faithful, reviewable record of what
was actually migrated, since half the transformation is per-row manual
override (id collisions, status corrections, verified repo names) that
cannot be derived mechanically from the sheet alone.

Populates only projects, diary_entries, and tech_stack_items. Does not
touch Deep Test or Architecture Map for any migrated project; those stay
empty until someone deliberately runs them later, same as any other
project.

Usage:
    python3 scripts/migrate_tool_registry.py --dry-run   # print the computed payload, no writes
    python3 scripts/migrate_tool_registry.py              # apply to Supabase via REST
"""
import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_DATE = "2026-07-05"
MIGRATION_ENTRY_DATE = "Jul 5"
EXISTING_PROJECT_IDS = {"knowledge-loom", "wayfinder"}

# ---------------------------------------------------------------------------
# Source rows, transcribed 1:1 from the Registry tab on the migration date.
# ---------------------------------------------------------------------------
ROWS = [
    {
        "id": "T001", "tool_name": "GitHub MCP Server", "venture": "Internal / Shared",
        "type": "MCP Server", "status": "Active",
        "description": "Custom MCP server hosted on Railway. Connects Claude to GitHub repos across all ventures.",
        "link": "https://github-mcp-server-production-4abf.up.railway.app/sse",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "mcp, github, railway", "notes": "SSE transport.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "SSE-transport MCP server on Railway. Supports file read/write, commits, PRs, branches, issues, repo search, code search across all ventures.",
        "future_plans": "Webhook support so GitHub events can trigger Claude actions.",
    },
    {
        "id": "T002", "tool_name": "Google Sheets MCP", "venture": "Internal / Shared",
        "type": "MCP Server", "status": "Active",
        "description": "Railway-hosted MCP server bridging Claude to Google Sheets via GAS.",
        "link": "https://gas-sheets-mcp-production-2a12.up.railway.app/mcp",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "mcp, sheets, railway, gas", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Railway MCP bridging Claude to Google Sheets via GAS bridge. Read rows, append, update, delete, clear, create sheet, list sheets, find rows.",
        "future_plans": "Add formatting and conditional formatting support.",
    },
    {
        "id": "T003", "tool_name": "GAS Developer MCP", "venture": "Internal / Shared",
        "type": "MCP Server", "status": "Active",
        "description": "MCP server for creating, reading, and deploying Google Apps Script projects from Claude.",
        "link": "https://gas-dev-mcp-production.up.railway.app/mcp",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "mcp, gas, railway, developer", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Railway MCP for managing GAS projects from Claude. Get/update project files, list projects, create project, run functions, list and create deployments.",
        "future_plans": "Remote script properties support.",
    },
    {
        "id": "T004", "tool_name": "Google Tasks MCP", "venture": "Internal / Shared",
        "type": "MCP Server", "status": "Active",
        "description": "Railway-hosted MCP server for reading and writing Google Tasks.",
        "link": "https://gas-tasks-mcp-production.up.railway.app/mcp",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "mcp, tasks, railway", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Railway MCP for Google Tasks. List task lists, list/create/complete/delete/update tasks.",
        "future_plans": "Subtask support and due date filtering.",
    },
    {
        "id": "T005", "tool_name": "LinkedIn Content Engine", "venture": "Prismm",
        "type": "GAS Web App", "status": "Active",
        "description": "GAS + Groq API + Railway/Puppeteer renderer. Generates LinkedIn posts and exports as JPEG.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "linkedin, groq, content, prismm", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "GAS + Groq API generates LinkedIn posts. Railway/Puppeteer renderer exports final post as JPEG for direct upload.",
        "future_plans": "Scheduling queue and multi-format export (stories, carousels).",
    },
    {
        "id": "T006", "tool_name": "BTC Compliance Manager", "venture": "Black Tech Capital",
        "type": "GAS Web App", "status": "Active",
        "description": "GAS web app with Groq AI integration, calendar views, and weekly email digests for BTC compliance.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "compliance, btc, groq, calendar", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "GAS web app with Groq AI integration, calendar views for compliance deadlines, and weekly email digests to the BTC team.",
        "future_plans": "LP reporting module and document upload tracking.",
    },
    {
        "id": "T007", "tool_name": "ReRev Initiatives Database", "venture": "ReRev Labs",
        "type": "Google Sheet System", "status": "Active",
        "description": "Master Google Sheet tracking all ReRev initiatives.",
        "link": "https://docs.google.com/spreadsheets/d/1Mvo3qP0KM1PgYl4rx8W9Dh2i78_9FmzHl5u-BHda8B0",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "rerev, tracking, initiatives", "notes": "",
        "app_script_id": "", "connected_sheets": "1Mvo3qP0KM1PgYl4rx8W9Dh2i78_9FmzHl5u-BHda8B0",
        "functionality": "Master Google Sheet tracking all ReRev initiatives. Status, owner, venture, links, and notes per initiative.",
        "future_plans": "Connect to Super Connector CRM as an initiative reference tab.",
    },
    {
        "id": "T008", "tool_name": "Knowledge Loom", "venture": "ReRev Labs",
        "type": "GAS Web App", "status": "Active",
        "description": "Content aggregation SaaS delivered to Founders Playground / Katherine. Supabase + GAS + Mailgun.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "saas, content, supabase, mailgun", "notes": "Delivered to client.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Content aggregation SaaS. GAS backend + Supabase DB + Mailgun newsletter delivery. GitHub Actions CI/CD pipeline.",
        "future_plans": "Delivered to client. No active roadmap.",
    },
    {
        "id": "T009", "tool_name": "Our Little Adventures", "venture": "Internal / Shared",
        "type": "GAS Web App", "status": "Active",
        "description": "Couples web app built with Anna. GAS + Google Sheets backend.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "personal, gas, sheets", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Couples web app built with Anna. Tracks shared adventures, memories, and plans.",
        "future_plans": "TBD - personal project.",
    },
    {
        "id": "T010", "tool_name": "Prismm ToFu Command", "venture": "Prismm",
        "type": "GAS Web App", "status": "Active",
        "description": "Top-of-funnel GTM operating system for Prismm sales.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "prismm, gtm, sales, tofu", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Top-of-funnel GTM OS for Prismm. Tracks cold outreach targets, ICP scoring, and contact discovery queue for community banks and credit unions ($250M-$2B asset tier).",
        "future_plans": "Apollo.io integration for contact enrichment.",
    },
    {
        "id": "T011", "tool_name": "Prismm MoFu Command", "venture": "Prismm",
        "type": "GAS Web App", "status": "Active",
        "description": "Mid-funnel GTM operating system for Prismm. Tracks warm leads and engagement.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "prismm, gtm, sales, mofu", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Mid-funnel GTM OS for Prismm. Tracks warm leads, engagement history, follow-up cadences, and demo pipeline.",
        "future_plans": "Auto-pull status from Prismm Sequence Review portal.",
    },
    {
        "id": "T012", "tool_name": "Prismm Relationship Manager", "venture": "Prismm",
        "type": "GAS Web App", "status": "Active",
        "description": "Relationship management layer for Prismm GTM OS.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "prismm, gtm, crm, relationships", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Relationship management layer for Prismm GTM. Tracks key contacts at target institutions, relationship health, last touchpoint, and next action.",
        "future_plans": "Merge with or link to Super Connector CRM.",
    },
    {
        "id": "T013", "tool_name": "Year of 1000 Rejections Workshop", "venture": "ReRev Labs",
        "type": "GAS Script", "status": "Active",
        "description": "Automated opportunity-discovery workshop system. GAS + Groq + local Mistral 7B via Colab.",
        "link": "", "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "rerev, groq, workshop, automation", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Automated opportunity-discovery workshop system. GAS + Groq for AI analysis. Local Mistral 7B via Google Colab for offline runs. Surfaces rejection patterns and pivot ideas.",
        "future_plans": "Package as a ReRev Labs client-facing workshop product.",
    },
    {
        "id": "T014", "tool_name": "Super Connector CRM", "venture": "ReRev Labs",
        "type": "GAS Web App", "status": "Active",
        "description": "Personal CRM vision for relationship intelligence. Analyzes email history.",
        "link": "https://script.google.com/a/macros/rerev.io/s/AKfycbwSlcg6PPFgDdNbmaZ82nYmsqGpdApYHO8c6mmACTF8wGgPO8FC74o4qZjvp0ZHuh0_PQ/exec",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-04-01T04:00:00.000Z",
        "tags": "rerev, crm, relationships, email",
        "notes": (
            "SESSION 5 COMPLETE (2026-04-01). Architecture: Sheets removed, Railway is source of truth. "
            "GitHub Pages app (keyona-rerev/super-connector-app) calls Railway directly from browser. "
            "GAS bridge handles automated ops. SEARCH FIXED: GET /contacts/search?q= ILIKE text endpoint, "
            "POST /search uses embed_query not embed_profile. GRID/LIST TOGGLE added. BUCKETS linked to "
            "initiatives via initiative_id field. NEW CONTACT FIELDS: imported_via (LinkedIn provenance), "
            "active_advocacy (Proactive Super Connections). POST /brain-dump endpoint on Railway for "
            "one-call session pushes. serverBrainDump() in Network CRM GAS. 14 initiatives pushed to "
            "Railway from April 1 brain dump. SC_API_KEY: [redacted, see Railway env]."
        ),
        "app_script_id": "144ZiIEVpxYrRB93wq4MoYgtUxqVDQdQ7ZdmHKQH3RGWu-thi8F-6v7hz",
        "connected_sheets": "1WO6YK2alMx7Wu49Vpm1NZBN5fdquNUmCvgpIhjNK10g",
        "functionality": (
            "Full Railway-backed CRM. FastAPI + pgvector on Railway. GitHub Pages front-end "
            "(keyona-rerev/super-connector-app). contacts-crm.js owns the full UI: Overview (buckets + "
            "follow-ups) and Browse All tabs, search, drawer, edit modal, bucket management. Search: text "
            "ILIKE on type (GET /contacts/search), semantic on explicit semantic trigger (POST /search with "
            "embed_query). Grid/list toggle. Buckets: create, add/remove contacts, link to initiatives. "
            "POST /brain-dump for batch session pushes. Contacts: imported_via + active_advocacy fields for "
            "LinkedIn import and Proactive Super Connections. All Railway endpoints: /contact, "
            "/contact/bulk, /contacts, /contacts/search, /search, /initiatives, /initiative, /sub-project, "
            "/stakeholder, /action-item, /follow-up, /bucket, /content, /event, /brain-dump."
        ),
        "future_plans": (
            "CRITICAL: Katherine's App (INI-1775079206634684). CRITICAL: Proactive Super Connections "
            "Feature (INI-1775079218546964), Active Advocacy Bucket, Google Form intake, recommendation "
            "engine. HIGH: Phoebe Daily Digest (change Mon/Thu to daily). HIGH: LinkedIn Network Import "
            "System (INI-177507922143847), CSV intake, imported_via field, overlap detection. HIGH: ReRev "
            "New Website. Phoebe daily digest cadence change. Content tab to Railway sync not built. "
            "Follow-up health scoring not built."
        ),
    },
    {
        "id": "T015", "tool_name": "Keyona's Tool Registry", "venture": "Internal / Shared",
        "type": "Google Sheet System", "status": "Active",
        "description": "Master sheet tracking every tool built across all ventures. The source of truth.",
        "link": "https://docs.google.com/spreadsheets/d/1ol8Yvpe454T4yHpEgy8PFjOAJvfyUDrKesgD_wM7m4o",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "meta, registry, internal", "notes": "",
        "app_script_id": "1tPYpisVbh_H30pc2PDsGT5jwxXT1uuiBio5_gSxBupoiuX1CyfHvmTDE",
        "connected_sheets": "1ol8Yvpe454T4yHpEgy8PFjOAJvfyUDrKesgD_wM7m4o",
        "functionality": "GAS web app second brain. Card and table views, search, filter by venture/type/status, add/edit/delete tools, changelog tab with Notes column, Discovery Skill prompt tab.",
        "future_plans": "REGISTRY_SKILL.md on GitHub needs updating with new columns and hardcoded sheet ID. End-of-session changelog trigger to be formalized as skill.",
    },
    {
        "id": "T016", "tool_name": "Prismm Sequence Review Site", "venture": "Prismm",
        "type": "GAS Web App", "status": "Active",
        "description": "GitHub Pages site for reviewing and approving Prismm email sequences. Martha and Shella notified on new pushes. Password protected.",
        "link": "https://keyona-rerev.github.io/prismm-sequence-review",
        "date_built": "2026-03-20T04:00:00.000Z", "last_used": "2026-03-20T04:00:00.000Z",
        "tags": "prismm, email, sequences, review, github pages",
        "notes": "Recipients: martha@getprismm.com, shella@getprismm.com. Password: [redacted]. Repo: keyona-rerev/prismm-sequence-review.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "GitHub Pages site for reviewing and approving Prismm email sequences. Martha and Shella notified by email on new push. Password protected. Approve/reject workflow with status badges and rejection pattern logging.",
        "future_plans": "Rejection pattern analytics view.",
    },
    {
        "id": "T017", "tool_name": "Content Idea Capture System", "venture": "Internal / Shared",
        "type": "Google Sheet System", "status": "Active",
        "description": "End-of-session and mid-conversation content idea logging system. Surfaces blog post and LinkedIn post candidates from conversations and logs them to the Initiatives sheet.",
        "link": "https://web-production-5fec3.up.railway.app/mcp",
        "date_built": "2026-03-23T04:00:00.000Z", "last_used": "2026-04-16T04:00:00.000Z",
        "tags": "content, linkedin, blog, ideas, skill, initiatives",
        "notes": "Content tools deployed to MCP server April 16 2026. Tools: sc_log_content_idea, sc_list_content_ideas, sc_get_content_idea. All hit Railway /content endpoint. 29 total tools on MCP. README pushed to keyona-rerev/super-connector-mcp.",
        "app_script_id": "", "connected_sheets": "1Mvo3qP0KM1PgYl4rx8W9Dh2i78_9FmzHl5u-BHda8B0",
        "functionality": "Two trigger modes: (1) Active, Keyona says CONTENT IDEA mid-conversation, Claude extracts idea and appends row to Content Ideas tab immediately. (2) Passive, end-of-session sweep scans conversation for article/LinkedIn candidates and batch-logs any not yet captured.",
        "future_plans": "GAS web app visual layer on top of Content Ideas tab. Status workflow automation. Collaborator notification on new ideas added.",
    },
    {
        "id": "T018", "tool_name": "Post-Meeting Intelligence Engine", "venture": "Internal / Shared",
        "type": "GAS Script", "status": "Active",
        "description": "Time-driven GAS trigger that processes Google Meet transcripts, extracts todos, updates Super Connector contacts, creates Gmail drafts, and sends a digest email, fully async.",
        "link": "", "date_built": "2026-03-24T04:00:00.000Z", "last_used": "2026-03-28T04:00:00.000Z",
        "tags": "automation, transcripts, tasks, superconnector, gmail, digest, meetings",
        "notes": "Trigger runs every 5 min. Scoped to transcript folder 1kU30t4XelF4f3HDi7h0dbrq5YIPf15tg. Script Properties: ANTHROPIC_API_KEY. Tasks API must be enabled. MeetingLog tab in Super Connector sheet tracks processed files. Calls super-connector-api-production.up.railway.app for vectorization.",
        "app_script_id": "1u3aNNWF9VBvEg8eouLIZUvC6DmtYPCk3t54JVOvl9IolFgMn2Nw2odB3",
        "connected_sheets": "1WO6YK2alMx7Wu49Vpm1NZBN5fdquNUmCvgpIhjNK10g",
        "functionality": (
            "5 files: Config.gs (all IDs + constants), ProcessingLog.gs (MeetingLog tab read/write), "
            "TranscriptProcessor.gs (Drive polling + Claude API call returning todos/contact_updates/"
            "follow_up_draft), OutputDispatcher.gs (routes todos to correct Google Tasks list, "
            "updates/creates Super Connector contacts + vectorizes via API, creates Gmail draft with "
            "meeting notes link embedded in body, sends HTML digest email), TriggerSetup.gs (installTrigger, "
            "testProcessFile, pingClaude utilities). Contact matching by email first, full name fallback. "
            "Stubs created for unknown contacts flagged Needs Review. Meeting notes Google Doc link "
            "appended near bottom of every follow-up draft. Time-aware prompting: Claude receives meeting "
            "date, send date, and days elapsed, instructed never to use relative time phrases (yesterday, "
            "earlier today, etc.). Secondary scrub pass via scrubRelativeTime() in OutputDispatcher catches "
            "any phrases that slip through."
        ),
        "future_plans": "Retroactive batch will self-complete as trigger runs through backlog. Next: proactive intro matching digest using /match endpoint on Super Connector API.",
    },
    {
        "id": "T019", "tool_name": "Prismm ABM Matrix", "venture": "Prismm",
        "type": "GAS Script", "status": "In Progress",
        "description": "ABM batch selection engine for Prismm cold outreach. Weekly batches of 20 target accounts (NATO phonetic naming), hypothesis-driven selection, automated Wednesday/Thursday/Friday email reports.",
        "link": "https://github.com/keyona-rerev/prismm-abm-matrix",
        "date_built": "2026-03-25T04:00:00.000Z", "last_used": "2026-03-25T04:00:00.000Z",
        "tags": "prismm, abm, outreach, gas, github, apollo, credit unions",
        "notes": "Architecture approved, build not yet executed. Schema confirmed: Pipeline, Batches, and ICP Mirror tabs to be added to Martha's sheet (1FN4NVRb7VfbUg7EO6G01cYm3p9-Q2jS1R9gNl_BU410), NOT a new sheet. ICP Mirror row 1 frozen with warning cell A1: DO NOT EDIT, auto-generated by ABM system. Pipeline.json = Google Sheet as operational layer, GitHub as weekly snapshot archive. Hypothesis stored inline in Batches tab. Awaiting build execution.",
        "app_script_id": "", "connected_sheets": "1FN4NVRb7VfbUg7EO6G01cYm3p9-Q2jS1R9gNl_BU410",
        "functionality": "GAS scripts: Wednesday batch selection email to Keyona (20 accounts + hypothesis), Thursday Action Report, Friday Performance Report. ICP Mirror tab pulls filtered records from Credit Unions tab. Batches tab tracks NATO-named batches with hypothesis, dates, and status. Pipeline tab is operational outreach tracker. GitHub repo holds weekly snapshot archives.",
        "future_plans": "Apollo.io API integration for contact enrichment and sequence execution. Batch performance analytics dashboard.",
    },
    {
        "id": "T020", "tool_name": "TikTok Transcription Worker", "venture": "Personal / Internal",
        "type": "Railway Cron Job", "status": "In Progress",
        "description": "Autonomous daily batch worker. Downloads 200 TikTok saved videos/day, transcribes via Whisper, deletes videos, saves transcripts to SQLite DB, uploads to Google Drive. Local search UI at localhost:5000.",
        "link": "", "date_built": "2026-03-26T04:00:00.000Z", "last_used": "2026-03-26T04:00:00.000Z",
        "tags": "tiktok, whisper, railway, cron, transcription, sqlite, personal",
        "notes": "Files in C:\\Users\\keyon\\Documents\\tiktok-railway. Setup paused at Part 1 (cookies encoding step). 2,080 videos total, ~11 day run at 200/day. GitHub repo not yet created. Local search UI files in C:\\Users\\keyon\\Documents\\tiktok-search.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Railway cron job (0 2 * * *). worker.py downloads batch of 200 TikToks via yt-dlp, transcribes with Whisper tiny model, deletes video files after transcription, saves transcripts to SQLite DB with FTS5 full-text search. Uploads tiktoks.db to Google Drive via service account after each batch. Fully resumable, skips already-processed videos. search_ui.py serves local web UI at localhost:5000 for keyword search across all transcripts.",
        "future_plans": "Complete Railway setup. Once all 2,080 videos are processed, consider building a smarter search UI with filters by creator, date saved, or topic cluster.",
    },
    {
        "id": "T022", "tool_name": "Phoebe Agent", "venture": "Cross-venture (BTC, ReRev Labs, Sekhmetic)",
        "type": "GAS Autonomous Agent", "status": "Active",
        "description": "Autonomous priority manager + email automation. Sends weekly check-ins, auto-parses email replies via Claude API, syncs changes to Initiatives sheet in real-time.",
        "link": "Bound to Initiatives Sheet (Extensions > Apps Script)",
        "date_built": "2026-03-29T00:00:00.000Z", "last_used": "2026-03-29T00:00:00.000Z",
        "tags": "phoebe, priority, email, automation, claude-api, initiatives",
        "notes": "Phase 3 complete. Email monitoring runs every 2 minutes. Check-ins Monday/Thursday 8am. Status decay scan every 6 hours.",
        "app_script_id": "Bound to Initiatives Sheet",
        "connected_sheets": "Initiatives (1Mvo3qP0KM1PgYl4rx8W9Dh2i78_9FmzHl5u-BHda8B0), Super Connector (1WO6YK2alMx7Wu49Vpm1NZBN5fdquNUmCvgpIhjNK10g)",
        "functionality": "Monday/Thursday check-in emails. Email reply monitoring (every 2 min). Intelligent parsing via Claude Opus. Auto-apply updates to sheets. Superconnections detection. Dashboard sidebar with quick actions. Status decay alerts every 6 hours.",
        "future_plans": "Phase 4: Burndown charts, calendar integration, webhook deployment, T022 dashboard, contact enrichment via T014",
    },
    {
        "id": "T023", "tool_name": "Network CRM Dashboard (Phase 6B + 6C)", "venture": "ReRev Labs",
        "type": "GAS Web App", "status": "Active",
        "description": "Full dashboard layer for Network CRM. Phase 6B: Kanban + Superconnections drag-drop board with detail panels, quick actions, activity log. Phase 6C: Bubble network visualization + 6-week pipeline burndown chart.",
        "link": "", "date_built": "2026-03-30T04:00:00.000Z", "last_used": "2026-03-30T04:00:00.000Z",
        "tags": "crm, dashboard, kanban, network-viz, burndown, superconnections",
        "notes": "Phase 6B deployed: drag-drop Kanban, detail panels, quick actions, activity log. Phase 6C deployed: bubble network viz, 6-week pipeline burndown. Both bound to Network CRM GAS Project.",
        "app_script_id": "", "connected_sheets": "1WO6YK2alMx7Wu49Vpm1NZBN5fdquNUmCvgpIhjNK10g",
        "functionality": "Phase 6B: Drag-drop Kanban board for initiative tracking, contact detail panels, quick actions (email, task, note), activity log. Phase 6C: Interactive bubble network visualization of contact relationships, 6-week pipeline burndown chart overlaying planned vs actual progress.",
        "future_plans": "Architecture review needed: unify Contacts tab (4,377 contacts, vectorized) and Stakeholders tab (~30-50 people, initiative-linked) into single contact record. Options: (A) consolidate Stakeholders into Contacts column, (B) make Stakeholders a filtered view, (C) merge into unified record with initiative linkage. Blocked pending data structure audit.",
    },
    {
        "id": "T024", "tool_name": "", "venture": "Internal",
        "type": "", "status": "Planned",
        "description": "When Phoebe processes a meeting transcript, look up contact ID in Railway by name or email, write conversation notes to contact_notes table, and update last_met date on the contact record. Sub-feature of T022 (Phoebe Agent).",
        "link": "", "date_built": "", "last_used": "",
        "tags": "", "notes": "",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "", "future_plans": "",
    },
    {
        "id": "T025", "tool_name": "BTC Webinar Outreach Tracker", "venture": "Black Tech Capital",
        "type": "GAS Script", "status": "Planned",
        "description": "Gmail label scanner that auto-logs outreach and reply status to Super Connector Railway contacts. Label: CTEL_Webinar_Collab.",
        "link": "", "date_built": "", "last_used": "",
        "tags": "btc, gmail, outreach, webinar, superconnector, railway, tracking, automation",
        "notes": "Gmail label: CTEL_Webinar_Collab. Build against BTC Gmail account (same account as Phoebe). Add as a new function in the existing Phoebe GAS project (Script ID: 1UeO72LgmCgEhr534Aw2ouj7lHKFiXe0mbGSCaFjsf1bphf510SOnkV4e) rather than a standalone deployment.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Time-driven trigger (every 15-30 min) scans BTC Gmail for threads with label CTEL_Webinar_Collab. For each labeled thread: extracts recipient email, matches to Super Connector contact via Railway GET /contacts/search, logs outreach date, subject line, and thread ID to contact record via PUT /contact/{id} appending outreach_log field. Second function checks labeled threads for inbound replies and updates reply status and days-since-outreach on the contact record. Surfaces non-responders after configurable window (e.g. 7 days).",
        "future_plans": "Surface non-responders in Phoebe daily briefing email. Extend label pattern to other BTC outreach campaigns (e.g. CTEL_LP_Outreach, CTEL_ExitLab_Guest) using same scanner architecture.",
    },
    {
        "id": "T026", "tool_name": "Proposal Maker (proposal-publisher)", "venture": "ReRev Labs",
        "type": "Skill + GitHub/Railway pipeline", "status": "Active",
        "description": "End-to-end proposal authoring and publishing system. Design HTML proposals in conversation with Claude, push to GitHub, Railway auto-deploys, live shareable URL returned in chat. No manual deploy step.",
        "link": "", "date_built": "2026-04-15T04:00:00.000Z", "last_used": "2026-04-30T04:00:00.000Z",
        "tags": "proposals, skill, github, railway, client-facing, html, rerev",
        "notes": "Lives as a user skill at /mnt/skills/user/proposal-publisher/SKILL.md. Trigger phrases: 'make a proposal', 'ship it', 'push it live', 'get me a link', 'publish this'. Uses ReRev/Prismm design system depending on venture context.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Skill-driven workflow: (1) design proposal/one-pager/pitch page in conversation as standalone HTML, (2) get Keyona's approval, (3) commit to GitHub repo, (4) Railway auto-deploys on push, (5) return live URL in chat. Handles output from GAS or any other automation that needs a sendable link. Standard ReRev/Prismm/BTC design tokens baked in.",
        "future_plans": "Template gallery for common proposal types. Auto-archive old proposals after N days. Productize as a consultant superpower offering.",
    },
    {
        "id": "T027", "tool_name": "Fathom Follow-Up System (Constance)", "venture": "Client Work",
        "type": "GAS Script", "status": "Active (manual)",
        "description": "Post-meeting follow-up automation built on Fathom API instead of Google Meet transcripts. Separate codebase from T018. Built for client Constance.",
        "link": "", "date_built": "2026-04-20T04:00:00.000Z", "last_used": "2026-04-25T04:00:00.000Z",
        "tags": "fathom, follow-up, client-work, gas, transcripts, automation, constance",
        "notes": "Distinct from T018. T018 reads Google Meet transcripts from Drive folder; this system pulls from Fathom API and is reconfigured to that data shape. Currently manual, installTrigger() not yet activated, pending confirmed end-to-end test.",
        "app_script_id": "1vcDe9QjKUxu0jjTWdc0RDW7Ef8DXCKw5hm7nurqED3prxdauTy7FLz8Z",
        "connected_sheets": "",
        "functionality": "GAS script that pulls meeting transcripts and metadata from Fathom API, parses with Claude API for action items and follow-up content, and generates draft follow-up emails. Architectural twin of T018 but rebuilt against Fathom's data model rather than Google Drive transcript files. Manually functional end-to-end; trigger activation pending.",
        "future_plans": "Activate installTrigger() after end-to-end test confirmation. Consider generalizing into a Fathom-based variant of T018 that any client using Fathom could deploy. Productize as a consultant superpower offering for Fathom users.",
    },
    {
        "id": "T028", "tool_name": "Online Presence Report Card", "venture": "ReRev Labs",
        "type": "Netlify Web App + Functions", "status": "Active",
        "description": "Lead-gen Pixie. Visitors enter name, email, pick a primary job (win clients / attract investors / get hired / build a public profile) plus optional secondary job, and get a graded report card of their online presence rendered as a gallery piece. Grades exclusively on what surfaces in indexed search results, not pages visited directly. Every run captures a lead in Supabase and emails the visitor their card. CTA drives to Keyona's Hubble booking link.",
        "link": "https://online-biz-report-card.netlify.app/",
        "date_built": "2026-06-01T04:00:00.000Z", "last_used": "2026-07-04T04:00:00.000Z",
        "tags": "rerev, lead-gen, pixie, report-card, netlify, railway, postgrest, resend, anthropic, turnstile, online-presence, audit",
        "notes": "MIGRATED OFF SUPABASE 2026-07-04. GitHub repo keyona-rerev/online-report-card, Netlify auto-deploys on push to main. Backend is now a self-hosted Postgres + PostgREST stack on Railway (project: online-report-card-backend, public API at postgrest-production-56ca.up.railway.app), not Supabase, moved to free up a Supabase free-tier project slot for Wayfinder. Old Supabase project (wkgadarpjeodlfhqpqeg) deleted. Schema: schema.sql in the repo (supabase.sql kept for history only, marked deprecated). Table report_cards (RLS on, token column for shareable pages) plus four sibling tables already provisioned on this same backend for the other Athlete Site Pixies: scholarship_reports, benchmark_reports, timeline_reports, eligibility_reports (T030-T033). Netlify env vars: ANTHROPIC_API_KEY, POSTGREST_URL (renamed from SUPABASE_URL), TURNSTILE_SECRET, DAILY_CAP, RESEND_API_KEY, EMAIL_FROM=reports@rerev.io, EMAIL_REPLY_TO=keyona@rerev.io. SUPABASE_SERVICE_KEY removed entirely, no longer needed, PostgREST anon role has full read/write on this dedicated backend. Gotcha for future Railway PostgREST deploys: the service domain needs an explicit port mapping (3000) or it 502s with 'connection refused' even though the container is healthy, Railway does not reliably auto-detect this for Docker-image services; setting a PORT env var alongside fixing the domain's port field is what got it to stick. All 38 real leads migrated and verified live. MODEL: claude-haiku-4-5-20251001. Web search max_uses=10 with broad-pass research framing. Temperature 0. Cache lock 30 days (vary email when testing). STANDING RULE: no building and no pushing to this repo without Keyona's explicit go-ahead, every time. Build and push are separate gates.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Static index.html with gated name+email form, primary job selector (clients/investors/hired/profile) + optional secondary job, channel chips for deliberate platform opt-outs (don't count against score), Turnstile widget. LinkedIn URL input removed, LinkedIn graded from indexed results only. Two Netlify Functions: POST /api/report (validate, Turnstile verify, daily cap, per-IP rate limit, 30-day cache, Haiku grade w/ web search, output validation, save lead to Supabase w/ token, Resend email) and GET /api/get-report?t=TOKEN. report.html is the shareable page w/ Download-as-PNG. Grading: indexed-search-results-only philosophy; N/A grades routed to Discoverability instead of pulling down composite; whole-letter grades on card face; B-tier in warm honey amber. Three bottom-of-card reads: narrative read, audience read, harmony read (secondary job only). Prose caps: narrative/audience_read/harmony 600 chars, first_read 280, findings 300. Defensive stripTags at render time; cached-card sanitization; real error stage/detail surfacing in report.js. Header labels (The Subject / Your Online Presence) removed.",
        "future_plans": "Re-grade prior users (open to-do on ReRev Labs tab). Wire into rerev.io (button or report.rerev.io subdomain). ABM campaign live targeting personal branding creators/coaches. Re-size DAILY_CAP against real usage at new Haiku pricing. Optional cache-bypass flag for testing. Keyona's own report posted to LinkedIn, three post variants drafted June 4.",
    },
    {
        "id": "T029", "tool_name": "MOFU Content Analyzer", "venture": "ReRev Labs",
        "type": "Audit / Report", "status": "In Progress",
        "description": "Lead-gen Pixel concept. Scrapes a B2B website, holds it against a defined target audience (ICP), and scores whether the site's middle-of-funnel content is doing its evaluation job. Returns a MOFU health scorecard with per-type scores, ranked gaps, and the next two or three pieces to build. Grounded in the Bessemer/Letteri content-capsule framework.",
        "link": "", "date_built": "", "last_used": "",
        "tags": "rerev, pixel, mofu, content-audit, lead-gen, scraper, icp, anthropic, web-search, planned",
        "notes": "Spec written 2026-06-13 (this session), build NOT started. Standalone tool, decided. Shares an engine shape with T028 Online Presence Report Card (Anthropic API + web search grading, report-card output, lead capture) but is built as its own tool, not a T028 mode. Distinct from T010 Prismm ToFu Command and T011 Prismm MoFu Command, which are GTM pipeline trackers, not content analyzers (name overlap only). Run a fresh REGISTRY check before any build.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Inputs: (1) a target-audience definition (preset ICP or freeform pains/gains/shift), (2) a site URL. Process: crawl site, classify each substantive page into one of five content-capsule types (symptom, solution-education, value-prop, customer/data story, product) or none; count pieces per type against the 2-3 prescription; run audience-fit and job-completion checks; score and generate a prioritized gap report. Per-type score 0-100 (presence+count 40, audience fit 30, job completion 30); overall weighted with a penalty for any type at zero. Four site-level diagnostics reported as flags: homepage drift (too broad or too feature-focused), messaging consistency vs how they sell, proof presence (quantified results/case studies), findability in search and gen-AI answers. Output framed as action, not just a number.",
        "future_plans": "Decide v1 scope: single-page homepage analyzer vs full-site crawl. Decide audience-input model: curated ICP presets vs freeform entry. Handle multi-job content pieces (tag both vs force primary). Optional messaging-consistency input (paste sales pitch to compare against site language). Decide lead-capture moment (score-then-gate vs email up front). Presets should cover ReRev's own ICPs (consultants, fractional execs, agencies, boutique advisors), not just Prismm's.",
    },
    {
        "id": "T030", "tool_name": "Scholarship Reality", "venture": "Athlete Site",
        "type": "Netlify Web App + Functions", "status": "In Progress",
        "description": "Lead-gen Pixie for athlete-site.com (Martha). Parent enters name, email, athlete's sport, and unweighted GPA; gets an honest read on what the scholarship is actually worth: realistic athletic-money picture for the sport next to the academic merit money the GPA unlocks. Captures a lead in Supabase, emails the parent their card, and fires an internal new-lead notification.",
        "link": "https://github.com/keyona-rerev/scholarship-reality",
        "date_built": "2026-06-16T04:00:00.000Z", "last_used": "2026-06-16T04:00:00.000Z",
        "tags": "athlete-site, martha, pixie, scholarship, lead-gen, netlify, supabase, resend, anthropic, haiku, turnstile, calculator",
        "notes": "Code pushed 2026-06-16, deploy not yet wired by Keyona. Martha's #1 pick of the 4 athlete Pixies (Scholarship > Competitive Benchmarker > Recruiting Timeline > Eligibility Quick Screen). Forked 1:1 from T028 Online Presence Report Card; ONLY the engine differs. Engine: DETERMINISTIC sourced data table (figures current to June 2026, post-House settlement: all D1 now equivalency, D2 unchanged, D3 no athletic aid) instead of live web-search grading. Haiku claude-haiku-4-5-20251001 temp 0 (NO web search) writes only the three reads; templated fallback if it fails. Dual email: parent gets clean subject 'your scholarship reality check'; Keyona gets internal notification subject '[T030 Scholarship Reality] New lead, name, sport gpa GPA' to LEAD_NOTIFY_TO. Supabase table scholarship_reports (RLS on, token column). Sender reports@rerev.io / reply keyona@rerev.io (rerev.io domain already verified in Resend). PENDING (Keyona manual): run supabase.sql, create Turnstile widget + replace YOUR_TURNSTILE_SITE_KEY in index.html, connect repo to Netlify, set env vars, point athlete-site domain. STANDING RULE inherited from T028: build and push are separate gates, explicit go each time. Athlete-site closeouts go under the Martha Underwood todo tab.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Static index.html (athlete-site skin: #0A0A0A bg, #FF4D00 accent, Inter + JetBrains Mono, corner brackets, grid overlay) with name+email gate, sport select (revenue vs equivalency optgroups), unweighted GPA, Turnstile. Two Netlify Functions: POST /api/report -> reality.js (validate -> Turnstile -> daily cap -> per-IP rate limit -> 30-day cache on email+sport+gpa -> compute from SPORTS table + academicTier -> Haiku reads -> save lead -> email parent + notify internal) and GET /api/get-report -> get-report.js. report.html is the shareable card with Download-as-PNG (html2canvas). Card shape: hero (typical athletic money), verdict + first read, six reality rows (any-aid <2%, full ride ~1%, sport athletic money, academic merit by GPA tier in accent, more-secure-money, all-sport avg $12.5K athletic vs $17K academic), three reads (athletic reality / what GPA unlocks / funding stack). Sourced numbers: golf ~$12.5K, wrestling ~$18K, women's rowing ~$25K, men's basketball ~$38K, hockey ~$55K; academic tiers 3.8+ $15K-full, 3.5-3.79 $8K-$25K, 3.0-3.49 $2.5K-$8K, below 3.0 need-based.",
        "future_plans": "Deploy + point athlete-site domain. Then build the other 3 athlete Pixies on this same chassis, Competitive Benchmarker next (Martha's #2). Optional: reskin card to light/cream theme; add Martha to LEAD_NOTIFY_TO; emailed funding-stack worksheet as the lead magnet.",
    },
    {
        "id": "T031", "tool_name": "Competitive Benchmarker", "venture": "Athlete Site",
        "type": "Netlify Web App + Functions", "status": "In Progress",
        "description": "Athlete Site lead-gen Pixie (Martha #2). Parent enters sport, event/position, the athlete's key metric, and grad year; tool benchmarks that number against real D1/D2/D3/NAIA recruiting standards and returns the division level it maps to, the gap to the next level, and an honest read on where the athlete stands.",
        "link": "https://github.com/keyona-rerev/competitive-benchmarker",
        "date_built": "2026-06-16T04:00:00.000Z", "last_used": "",
        "tags": "athlete-site, martha, pixie, benchmarking, recruiting-standards, lead-gen, netlify, supabase, planned",
        "notes": "Spec written 2026-06-16 (athlete-pixies-build-plan.md). Build NOT started. Fork T030 chassis 1:1; swap engine to deterministic benchmark tables of recruiting standards by sport/event/division + Haiku narrative reads. SOURCING REQUIRED at build: current published time/mark/combine standards per sport and division (verify live, not training data). Start with measurable sports (track, swim, football combine); flag subjective/team sports for a coach-eye path. UPDATED 2026-07-04: T028's backend moved off Supabase to Railway (Postgres + PostgREST, project online-report-card-backend). The benchmark_reports table is already provisioned on that same Railway backend (see schema.sql in the online-report-card repo), no new database setup needed, just point this build's env vars at POSTGREST_URL from that Railway project. Repo planned: keyona-rerev/competitive-benchmarker. Build/push separate gates. Closeout under Martha Underwood tab. Run fresh REGISTRY check before build.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Same two-function Netlify chassis as T030. Inputs: sport, event/position, metric, grad year, gender where it splits standards. Deterministic benchmark table matches the metric to a division band; card hero = division level the number maps to; rows = metric vs each division cutoff + gap to next level; three Haiku reads (where they stand / realistic next level / how coaches use the number). Athlete-site skin, Download-as-PNG, dual email (clean parent subject + [T031] internal notification).",
        "future_plans": "v1 sport/event scope TBD. Handle subjective sports. Single vs multiple metrics. Gender splits.",
    },
    {
        "id": "T032", "tool_name": "Recruiting Timeline Checker", "venture": "Athlete Site",
        "type": "Netlify Web App + Functions", "status": "In Progress",
        "description": "Athlete Site lead-gen Pixie (Martha #3). The 'are we behind' timeline-anxiety play. Parent enters grad year and sport; tool computes against today's date and returns an on-track / behind / crunch-time verdict with what should already be done, what's next, and the key dates ahead.",
        "link": "https://github.com/keyona-rerev/recruiting-timeline",
        "date_built": "2026-06-16T04:00:00.000Z", "last_used": "",
        "tags": "athlete-site, martha, pixie, recruiting-timeline, milestones, lead-gen, netlify, supabase, planned",
        "notes": "Spec written 2026-06-16 (athlete-pixies-build-plan.md). Build NOT started. Fork T030 chassis; swap engine to deterministic recruiting-calendar/milestone rules keyed to grade level + NCAA contact-period reality + Haiku reads. SOURCING REQUIRED at build: current NCAA recruiting calendar and contact rules (changed, vary by sport/division) plus best-practice milestone timeline by grade. Verify live. UPDATED 2026-07-04: T028's backend moved off Supabase to Railway (Postgres + PostgREST, project online-report-card-backend). The timeline_reports table is already provisioned on that same Railway backend (see schema.sql in the online-report-card repo), no new database setup needed, just point this build's env vars at POSTGREST_URL from that Railway project. Repo planned: keyona-rerev/recruiting-timeline. Build/push separate gates. Closeout under Martha Underwood tab.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Same chassis as T030. Inputs: grad year, sport, current grade. Deterministic timeline rules vs today's date; card hero = On Track / Behind / Crunch Time; rows = what should be done by now (film, outreach, camps, NCAA Eligibility Center registration, transcript/test, visit windows), what's next, key dates; three Haiku reads ending in the three things to do this month. Athlete-site skin, Download-as-PNG, dual email.",
        "future_plans": "Sport-specific calendars vs general. Division targeting. Milestone granularity.",
    },
    {
        "id": "T033", "tool_name": "Eligibility Quick Screen", "venture": "Athlete Site",
        "type": "Netlify Web App + Functions", "status": "In Progress",
        "description": "Athlete Site lead-gen Pixie (Martha #4). NCAA initial-eligibility risk flags. Parent enters division target, core-course progress, core GPA, and grad year; tool returns an On Track / At Risk / Off Track read with the specific flags and next steps. Risk guidance only, not an official determination.",
        "link": "https://github.com/keyona-rerev/eligibility-screen",
        "date_built": "2026-06-16T04:00:00.000Z", "last_used": "",
        "tags": "athlete-site, martha, pixie, ncaa-eligibility, core-courses, lead-gen, netlify, supabase, planned",
        "notes": "Spec written 2026-06-16 (athlete-pixies-build-plan.md). Build NOT started. Fork T030 chassis; swap engine to deterministic NCAA initial-eligibility rules engine (16 core courses, core-GPA sliding scale / DII floor, progression timing) + Haiku plain-language flags. SOURCING REQUIRED at build: current NCAA DI/DII initial-eligibility requirements from the NCAA Eligibility Center (standardized test no longer required; sliding scale shifts). MUST verify live. FRAMING CAVEAT: risk flags only, never promise eligibility, always point to the NCAA Eligibility Center. UPDATED 2026-07-04: T028's backend moved off Supabase to Railway (Postgres + PostgREST, project online-report-card-backend). The eligibility_reports table is already provisioned on that same Railway backend (see schema.sql in the online-report-card repo), no new database setup needed, just point this build's env vars at POSTGREST_URL from that Railway project. Repo planned: keyona-rerev/eligibility-screen. Build/push separate gates. Closeout under Martha Underwood tab.",
        "app_script_id": "", "connected_sheets": "",
        "functionality": "Same chassis as T030. Inputs: division target (DI/DII), core-course progress vs 16, core GPA, grad year, optional test toggle. Deterministic eligibility rules engine; card hero = eligibility risk read; rows = core-course status, core GPA vs requirement, timing flags, registration reminder; three Haiku reads explaining each flag + next step. Athlete-site skin, Download-as-PNG, dual email.",
        "future_plans": "DI/DII only vs add NAIA. Core-course detail depth. Optional test-score input.",
    },
]

# ---------------------------------------------------------------------------
# Per-row overrides that cannot be derived mechanically from the sheet alone.
# ---------------------------------------------------------------------------
NAME_OVERRIDES = {
    "T024": "Phoebe Contact Notes Sync",
}
ID_OVERRIDES = {
    # "Knowledge Loom" slugifies to "knowledge-loom", already taken by the
    # existing Knowledge Loom Prismm project. Disambiguate using the real
    # repo name (kzobre/knowledge-loom-fp, fp = Founders Playground).
    "T008": "knowledge-loom-fp",
    # Blank Tool Name; derived from the Description per the migration spec.
    "T024": "phoebe-contact-notes-subfeature",
}
VENTURE_MAP = {
    "Prismm": "Prismm",
    "Black Tech Capital": "BTC",
    "ReRev Labs": "ReRev Labs",
    "Athlete Site": "Athlete Site",
    "Internal / Shared": "Internal",
    "Internal": "Internal",
    "Personal / Internal": "Personal",
    "Client Work": "Client Work",
    "Cross-venture (BTC, ReRev Labs, Sekhmetic)": "Internal",
}
# Verified directly against the real GitHub repo list; do not re-derive from
# the sheet's Link column, which is stale/wrong in at least one confirmed case.
REPO_OVERRIDES = {
    "T001": "keyona-rerev/github-mcp-server",
    "T002": "keyona-rerev/gas-sheets-mcp",
    "T003": "keyona-rerev/gas-dev-mcp",
    "T004": "keyona-rerev/gas-tasks-mcp",
    "T005": "keyona-rerev/prismm-renderer",
    "T008": "kzobre/knowledge-loom-fp",
    "T014": "keyona-rerev/super-connector-api",
    "T016": "keyona-rerev/prismm-sequence-review",
    "T017": "keyona-rerev/super-connector-mcp",
    "T026": "keyona-rerev/proposals-server",
    "T028": "keyona-rerev/online-report-card",
    "T030": "keyona-rerev/scholarship-reality",
    "T031": "keyona-rerev/competitive-benchmarker",
    "T032": "keyona-rerev/recruiting-timeline",
    "T033": "keyona-rerev/eligibility-screen",
    # T019's Link column points at keyona-rerev/prismm-abm-matrix, verified
    # not to exist. Leave null rather than trust a stale sheet value.
}
T014_EXTRA_REPOS = ["keyona-rerev/super-connector-app", "keyona-rerev/super-connector-mcp"]

BUILD_NOT_STARTED_PATTERNS = [
    re.compile(r"build\s+not\s+started", re.I),
    re.compile(r"build\s+NOT\s+started"),
    re.compile(r"awaiting\s+build\s+execution", re.I),
    re.compile(r"build\s+not\s+yet\s+executed", re.I),
]


def slugify(s):
    slug = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return slug or "project"


def project_id_for(row):
    if row["id"] in ID_OVERRIDES:
        return ID_OVERRIDES[row["id"]]
    name = row["tool_name"] or row["description"]
    pid = slugify(name)
    if pid in EXISTING_PROJECT_IDS:
        raise SystemExit(f"Unresolved id collision for {row['id']}: '{pid}' already exists.")
    return pid


def project_name_for(row):
    return NAME_OVERRIDES.get(row["id"], row["tool_name"])


def map_venture(v):
    if v not in VENTURE_MAP:
        raise SystemExit(f"Unmapped venture '{v}', add it to VENTURE_MAP before running.")
    return VENTURE_MAP[v]


def map_status(row):
    if row["id"] == "T015":
        return "Parked"  # special case: the registry itself, retired by this migration
    text = f"{row['notes']} {row['description']}"
    if any(p.search(text) for p in BUILD_NOT_STARTED_PATTERNS):
        return "Parked"
    default = {
        "Active": "Live",
        "Active (manual)": "Live",
        "In Progress": "Building",
        "Planned": "Parked",
    }
    if row["status"] not in default:
        raise SystemExit(f"Unmapped status '{row['status']}' for {row['id']}.")
    return default[row["status"]]


def relative_activity(last_used_iso, today):
    if not last_used_iso:
        return "Migrated from registry"
    last_used = datetime.fromisoformat(last_used_iso.replace("Z", "+00:00")).date()
    days_ago = (today - last_used).days
    if days_ago <= 0:
        return "Today"
    if days_ago == 1:
        return "Yesterday"
    if days_ago < 7:
        return f"{days_ago} days ago"
    if days_ago < 30:
        return f"About {days_ago // 7} weeks ago"
    if days_ago < 365:
        return f"About {round(days_ago / 30.44)} months ago"
    return f"About {round(days_ago / 365.25)} years ago"


def build_diary_body(row, project_id):
    lines = [
        f"Migrated from Tool Registry ({row['id']}).",
        f"Type: {row['type']}",
        f"Tags: {row['tags']}",
        f"Functionality: {row['functionality']}",
        f"Future Plans: {row['future_plans']}",
        f"Notes: {row['notes']}",
    ]
    if row["id"] == "T015":
        lines.append(f"Superseded by Wayfinder on {MIGRATION_DATE}. This Tool Registry sheet is now retired and kept only as a frozen historical record.")
    if row["id"] == "T008":
        lines.append(
            "keyona-rerev/knowledge-loom-gen is likely the template this was generated from, not the "
            "delivered tool. keyona-rerev/Founder-s-Playground-Content-App- is a superseded first version, "
            "not the current repo. Current repo is kzobre/knowledge-loom-fp."
        )
    return "\n".join(lines)


SERVICE_NAME_RULES = [
    ("railway.app", "Railway"),
    ("netlify.app", "Netlify"),
    ("github.io", "GitHub Pages"),
    ("docs.google.com/spreadsheets", "Google Sheet"),
    ("script.google.com", "Google Apps Script"),
    ("github.com", "GitHub"),
]


def service_name_for_url(url):
    for needle, name in SERVICE_NAME_RULES:
        if needle in url:
            return name
    return "Link"


def looks_like_url(value):
    return value.startswith("http://") or value.startswith("https://")


def looks_like_id(value):
    # Guards against descriptive placeholder text landing in an ID column
    # (e.g. T022's App Script ID literally reads "Bound to Initiatives Sheet").
    return bool(value) and " " not in value


def build_tech_stack_rows(row, project_id, repo_full_name):
    rows = []
    tool_name = project_name_for(row)
    link = row["link"]
    link_covers_repo = False

    if looks_like_url(link):
        # T019's Link points at a repo confirmed not to exist; don't publish a dead link.
        if not (row["id"] == "T019"):
            rows.append({
                "project_id": project_id, "service_name": service_name_for_url(link),
                "resource_label": tool_name, "link_url": link, "notes": None,
            })
            if repo_full_name and repo_full_name in link:
                link_covers_repo = True

    if repo_full_name and not link_covers_repo:
        rows.append({
            "project_id": project_id, "service_name": "GitHub",
            "resource_label": tool_name, "link_url": f"https://github.com/{repo_full_name}", "notes": None,
        })

    if row["id"] == "T014":
        for extra_repo in T014_EXTRA_REPOS:
            rows.append({
                "project_id": project_id, "service_name": "GitHub",
                "resource_label": extra_repo, "link_url": f"https://github.com/{extra_repo}", "notes": None,
            })

    app_script_id = row["app_script_id"]
    if looks_like_id(app_script_id) and app_script_id not in link:
        rows.append({
            "project_id": project_id, "service_name": "Google Apps Script",
            "resource_label": app_script_id, "link_url": f"https://script.google.com/d/{app_script_id}/edit",
            "notes": None,
        })

    connected_sheets = row["connected_sheets"]
    if connected_sheets:
        for chunk in connected_sheets.split(","):
            chunk = chunk.strip()
            m = re.search(r"([a-zA-Z0-9_-]{20,})", chunk)
            if not m:
                continue
            sheet_id = m.group(1)
            if sheet_id in link:
                continue  # already covered by the Link-derived row above
            label_match = re.match(r"^([^(]+)\(", chunk)
            resource_label = f"{label_match.group(1).strip()} sheet" if label_match else sheet_id
            rows.append({
                "project_id": project_id, "service_name": "Google Sheet",
                "resource_label": resource_label,
                "link_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}", "notes": None,
            })

    return rows


def build_project_row(row, today):
    project_id = project_id_for(row)
    repo_full_name = REPO_OVERRIDES.get(row["id"])
    out = {
        "id": project_id,
        "name": project_name_for(row),
        "venture": map_venture(row["venture"]),
        "status": map_status(row),
        "signal": "clean",
        "last_signal": "Resolved",
        "last_activity": relative_activity(row["last_used"], today),
        "goal": row["description"],
        "map_type": "tree",
        "repo_full_name": repo_full_name,
        "analysis_status": "not_requested",
    }
    if row["date_built"]:
        out["created_at"] = row["date_built"]
    return out, repo_full_name


def build_payload(today):
    projects, diary_entries, tech_stack_items = [], [], []
    for row in ROWS:
        project_row, repo_full_name = build_project_row(row, today)
        projects.append(project_row)
        diary_entries.append({
            "project_id": project_row["id"],
            "entry_date": MIGRATION_ENTRY_DATE,
            "signal": "clean",
            "source": "keyona",
            "kind": "import",
            "author": "Keyona Meeks",
            "body": build_diary_body(row, project_row["id"]),
        })
        tech_stack_items.extend(build_tech_stack_rows(row, project_row["id"], repo_full_name))
    return {"projects": projects, "diary_entries": diary_entries, "tech_stack_items": tech_stack_items}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print the computed payload as JSON instead of writing to Supabase")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    payload = build_payload(today)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        print(
            f"\n{len(payload['projects'])} projects, {len(payload['diary_entries'])} diary entries, "
            f"{len(payload['tech_stack_items'])} tech stack items computed."
        )
        return

    supabase_url, supabase_key = load_config()
    for table in ("projects", "diary_entries", "tech_stack_items"):
        rows = payload[table]
        for i in range(0, len(rows), args.batch_size):
            rest_post(supabase_url, supabase_key, table, rows[i:i + args.batch_size], extra_headers={"Prefer": "return=minimal"})
    print(
        f"Migrated {len(payload['projects'])} projects, {len(payload['diary_entries'])} diary entries, "
        f"{len(payload['tech_stack_items'])} tech stack items from the Tool Registry."
    )


if __name__ == "__main__":
    main()
