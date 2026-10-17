-- Chay 1 lan trong Supabase > SQL Editor: ho tro nhieu page.
-- Thay <PAGE_ID_QUY_NHON> bang FB_PAGE_ID hien tai (du lieu cu thuoc Quy Nhon).
alter table public.fb_page_daily add column if not exists page_id text;
update public.fb_page_daily set page_id = '<PAGE_ID_QUY_NHON>' where page_id is null;
alter table public.fb_page_daily alter column page_id set not null;
alter table public.fb_page_daily drop constraint if exists fb_page_daily_pkey;
alter table public.fb_page_daily add primary key (page_id, day);
