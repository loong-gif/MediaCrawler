begin;

alter table public.weibo_creators
    add column if not exists note_count integer not null default 0;

update public.weibo_creators wc
set note_count = coalesce(note_counts.note_count, 0)
from (
    select user_id, count(*)::integer as note_count
    from public.weibo_notes
    group by user_id
) as note_counts
where wc.user_id = note_counts.user_id;

update public.weibo_creators
set note_count = 0
where note_count is null;

create index if not exists idx_weibo_creators_note_count
    on public.weibo_creators (note_count);

create or replace function public.sync_weibo_creator_note_count()
returns trigger
language plpgsql
as $$
declare
    target_user_id bigint;
begin
    if tg_op = 'DELETE' then
        target_user_id := old.user_id;
    else
        target_user_id := new.user_id;
    end if;

    update public.weibo_creators wc
    set note_count = (
        select count(*)::integer
        from public.weibo_notes wn
        where wn.user_id = target_user_id
    )
    where wc.user_id = target_user_id;

    if tg_op = 'UPDATE' and old.user_id is distinct from new.user_id then
        update public.weibo_creators wc
        set note_count = (
            select count(*)::integer
            from public.weibo_notes wn
            where wn.user_id = old.user_id
        )
        where wc.user_id = old.user_id;
    end if;

    return null;
end;
$$;

drop trigger if exists trg_weibo_notes_sync_creator_note_count on public.weibo_notes;
create trigger trg_weibo_notes_sync_creator_note_count
after insert or update or delete on public.weibo_notes
for each row
execute function public.sync_weibo_creator_note_count();

commit;
