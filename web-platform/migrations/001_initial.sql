-- CareerFlow Web Platform schema. Apply inside a dedicated Supabase project.
create extension if not exists pgcrypto;

create table if not exists candidate_profiles (
  user_id text primary key,
  profile jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '[]'::jsonb,
  confirmed boolean not null default false,
  source_artifact_id text,
  updated_at timestamptz not null default now()
);

create table if not exists resume_templates (
  id text primary key,
  user_id text not null,
  template_id text not null default 'default',
  source_object_key text not null,
  profile_object_key text not null,
  source_sha256 text not null check (source_sha256 ~ '^[a-f0-9]{64}$'),
  source_filename text not null,
  document_format text not null check (document_format in ('pdf','docx')),
  created_at timestamptz not null default now(),
  unique(user_id, template_id)
);

create table if not exists applications (
  id text primary key,
  user_id text not null,
  company text not null,
  role text not null,
  jd text not null,
  stage text not null check (stage in ('onboarding','created','drafted','approved','built','submitted','interviewing','closed')),
  history jsonb not null default '[]'::jsonb,
  draft_bundle jsonb,
  document_plan jsonb,
  active_output_version text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists ix_applications_user_updated on applications(user_id, updated_at desc);

create table if not exists approvals (
  id text primary key,
  application_id text not null references applications(id) on delete cascade,
  user_id text not null,
  bundle_hash text not null check (bundle_hash ~ '^[a-f0-9]{64}$'),
  valid boolean not null default true,
  confirmed_at timestamptz not null default now()
);
create index if not exists ix_approvals_application on approvals(application_id);

create table if not exists artifacts (
  id text primary key,
  user_id text not null,
  application_id text references applications(id) on delete cascade,
  kind text not null,
  version_id text not null,
  object_key text not null unique,
  sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
  size_bytes bigint not null check (size_bytes >= 0),
  content_type text not null,
  active boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists ix_artifacts_owner on artifacts(user_id, application_id, active);

create table if not exists provider_credentials (
  id text primary key,
  user_id text not null,
  session_id text,
  provider text not null,
  ciphertext bytea not null,
  nonce bytea not null,
  key_version integer not null,
  key_last_four text not null,
  base_url text not null,
  model text not null,
  persistent boolean not null default false,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id, session_id, provider)
);

create table if not exists agent_runs (
  id text primary key,
  user_id text not null,
  application_id text references applications(id) on delete cascade,
  run_type text not null,
  provider text not null,
  model text not null,
  status text not null check (status in ('queued','running','succeeded','failed','needs_attention')),
  idempotency_key text not null,
  usage jsonb not null default '{}'::jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  unique(user_id, idempotency_key)
);

create table if not exists document_jobs (
  id text primary key,
  user_id text not null,
  application_id text,
  action text not null check (action in ('inspect','build')),
  source_sha256 text not null,
  token_jti text not null unique,
  consumed boolean not null default false,
  status text not null check (status in ('queued','running','succeeded','failed')),
  output_prefix text not null,
  result jsonb not null default '{}'::jsonb,
  expires_at timestamptz not null
);

create table if not exists reviews (
  id text primary key,
  user_id text not null,
  application_id text not null unique references applications(id) on delete cascade,
  outcome text not null check (outcome in ('rejected','withdrew','offer','pending')),
  raw_feedback jsonb not null,
  category text not null,
  coaching jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- The public browser never receives direct table access. All reads/writes go through FastAPI.
alter table candidate_profiles enable row level security;
alter table resume_templates enable row level security;
alter table applications enable row level security;
alter table approvals enable row level security;
alter table artifacts enable row level security;
alter table provider_credentials enable row level security;
alter table agent_runs enable row level security;
alter table document_jobs enable row level security;
alter table reviews enable row level security;

revoke all on all tables in schema public from anon, authenticated;

