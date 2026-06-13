create table if not exists public.weibo_creators (
    user_id bigint primary key,
    nickname text not null,
    gender text not null,
    avatar text not null,
    "desc" text null,
    ip_location text null,
    follows integer not null,
    fans text not null,
    tag_list text null,
    note_count integer not null default 0,
    last_modify_ts bigint not null
);

create index if not exists idx_weibo_creators_last_modify_ts
    on public.weibo_creators (last_modify_ts);

create index if not exists idx_weibo_creators_note_count
    on public.weibo_creators (note_count);

create table if not exists public.weibo_notes (
    note_id bigint primary key,
    content text not null,
    create_time bigint not null,
    create_date_time timestamptz not null,
    liked_count bigint not null,
    comments_count bigint not null,
    shared_count bigint not null,
    last_modify_ts bigint not null,
    note_url text not null,
    ip_location text null,
    image_list jsonb not null default '[]'::jsonb,
    user_id bigint not null references public.weibo_creators (user_id),
    nickname text not null,
    gender text not null,
    profile_url text not null
);

create index if not exists idx_weibo_notes_user_id
    on public.weibo_notes (user_id);

create index if not exists idx_weibo_notes_create_time
    on public.weibo_notes (create_time);

create index if not exists idx_weibo_notes_create_date_time
    on public.weibo_notes (create_date_time);

create index if not exists idx_weibo_notes_last_modify_ts
    on public.weibo_notes (last_modify_ts);
