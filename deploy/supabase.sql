-- Run once in Supabase SQL Editor. Only the server's service_role may access it.
create table if not exists public.demo_runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  payload jsonb not null default '{"status":"PENDING"}'::jsonb
);
alter table public.demo_runs enable row level security;
revoke all on public.demo_runs from anon, authenticated;
grant select, insert, update on public.demo_runs to service_role;
create index if not exists demo_runs_created_at on public.demo_runs(created_at);

create or replace function public.claim_demo_run()
returns setof public.demo_runs
language plpgsql security definer set search_path = public
as $$
begin
  perform pg_advisory_xact_lock(773103450);
  -- Hard cap persists across restarts. No paid automatic expansion.
  if (select count(*) from public.demo_runs
      where created_at >= date_trunc('day', now() at time zone 'UTC') at time zone 'UTC') >= 20 then
    return;
  end if;
  return query insert into public.demo_runs default values returning *;
end;
$$;
revoke all on function public.claim_demo_run() from public, anon, authenticated;
grant execute on function public.claim_demo_run() to service_role;
