-- Wayfinder Supabase schema (project: ueosmjwumqqyswmnbyji)
-- Applied via migrations: init_projects_schema, seed_initial_projects,
-- add_session_log_entries, add_rubric_evolution_log, add_architecture_map_tables.
-- No custom backend: this is a static site calling PostgREST directly with
-- the anon key, so RLS policies grant the anon role full access rather than
-- gating on auth (single-user internal tool).

create table projects (
  id text primary key,
  name text not null,
  venture text not null,
  status text not null check (status in ('Active','Building','Stable','Blocked')),
  signal text not null check (signal in ('spiral','friction','clean','breakthrough')),
  last_signal text not null,
  last_activity text not null,
  goal text not null default '',
  map_type text not null default 'tree' check (map_type in ('tree','graph')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table rubric_lenses (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  lens_order int not null,
  name text not null,
  description text not null
);

create table diary_entries (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  entry_date text not null,
  signal text not null check (signal in ('spiral','friction','clean','breakthrough')),
  source text not null default 'keyona' check (source in ('keyona','client')),
  kind text not null default 'process',
  author text not null default 'Keyona Meeks',
  body text not null,
  created_at timestamptz not null default now()
);

create table session_log_entries (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  session_label text not null default 'Session',
  session_url text not null,
  bullets jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table rubric_evolution_log (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  lens_name text not null,
  old_description text not null,
  new_description text not null,
  changed_at timestamptz not null default now()
);

create table architecture_snapshots (
  project_id text primary key references projects(id) on delete cascade,
  files_parsed int not null,
  node_count int not null,
  edge_count int not null,
  generated_at timestamptz not null default now()
);

create table architecture_nodes (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  kind text not null check (kind in ('File','Function','Class')),
  name text not null,
  qualified_name text not null,
  file_path text not null,
  line_start int,
  line_end int,
  language text,
  parent_name text,
  unique(project_id, qualified_name)
);

create table architecture_edges (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  kind text not null default 'IMPORTS_FROM',
  source_qualified text not null,
  target_qualified text not null,
  file_path text not null,
  line int,
  resolved boolean not null default false
);

create index architecture_nodes_project_idx on architecture_nodes(project_id);
create index architecture_edges_project_idx on architecture_edges(project_id);

alter table projects enable row level security;
alter table rubric_lenses enable row level security;
alter table diary_entries enable row level security;
alter table session_log_entries enable row level security;
alter table rubric_evolution_log enable row level security;
alter table architecture_snapshots enable row level security;
alter table architecture_nodes enable row level security;
alter table architecture_edges enable row level security;

create policy "anon full access" on projects for all using (true) with check (true);
create policy "anon full access" on rubric_lenses for all using (true) with check (true);
create policy "anon full access" on diary_entries for all using (true) with check (true);
create policy "anon full access" on session_log_entries for all using (true) with check (true);
create policy "anon full access" on rubric_evolution_log for all using (true) with check (true);
create policy "anon full access" on architecture_snapshots for all using (true) with check (true);
create policy "anon full access" on architecture_nodes for all using (true) with check (true);
create policy "anon full access" on architecture_edges for all using (true) with check (true);
