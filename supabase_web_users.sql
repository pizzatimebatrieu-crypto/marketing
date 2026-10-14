-- Chay trong Supabase > SQL Editor
create table if not exists public.web_users (
  id            uuid primary key default gen_random_uuid(),
  username      text not null unique check (username = lower(username)),
  password_hash text not null,
  is_active     boolean not null default true,
  failed_count  int not null default 0,
  locked_until  timestamptz,
  created_at    timestamptz not null default now()
);

-- Bat RLS va KHONG tao policy: anon/authenticated key khong doc duoc bang nay.
-- Chi server dung service_role key moi truy cap (service_role bo qua RLS).
alter table public.web_users enable row level security;
