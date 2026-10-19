-- Chay 1 lan trong Supabase > SQL Editor: bang so lieu TikTok theo ngay.
create table if not exists public.tiktok_daily (
  day date primary key,
  video_views integer not null default 0,
  profile_views integer not null default 0,
  likes integer not null default 0,
  comments integer not null default 0,
  shares integer not null default 0
);
alter table public.tiktok_daily enable row level security;
