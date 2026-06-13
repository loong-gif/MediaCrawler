begin;
set local search_path = public;
create table if not exists public.weibo_note_comments (
    comment_id bigint primary key,
    note_id bigint not null references public.weibo_notes (note_id),
    user_id bigint null,
    nickname text null,
    gender text null,
    profile_url text null,
    avatar text null,
    content text not null,
    create_time bigint not null,
    create_date_time timestamptz not null,
    comment_like_count bigint not null default 0,
    sub_comment_count bigint not null default 0,
    parent_comment_id text null,
    ip_location text null,
    last_modify_ts bigint not null
);
create index if not exists idx_weibo_note_comments_note_id on public.weibo_note_comments (note_id);
create index if not exists idx_weibo_note_comments_user_id on public.weibo_note_comments (user_id);
create index if not exists idx_weibo_note_comments_create_time on public.weibo_note_comments (create_time);
create index if not exists idx_weibo_note_comments_last_modify_ts on public.weibo_note_comments (last_modify_ts);
commit;
