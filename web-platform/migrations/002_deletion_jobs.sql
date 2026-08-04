create table if not exists public.deletion_jobs (
  id text primary key,
  user_id text not null,
  scope text not null check (scope in ('account', 'application')),
  resource_id text not null default '',
  status text not null default 'pending',
  attempts integer not null default 0,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, scope, resource_id)
);

create index if not exists ix_deletion_jobs_user_id on public.deletion_jobs(user_id);
alter table public.deletion_jobs enable row level security;
revoke all on table public.deletion_jobs from anon, authenticated;

create table if not exists public.task_leases (
  id text primary key,
  user_id text not null,
  kind text not null check (kind in ('agent', 'document')),
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  unique (user_id, kind)
);

create index if not exists ix_task_leases_user_id on public.task_leases(user_id);
alter table public.task_leases enable row level security;
revoke all on table public.task_leases from anon, authenticated;

alter table public.document_jobs add column if not exists created_at timestamptz not null default now();
