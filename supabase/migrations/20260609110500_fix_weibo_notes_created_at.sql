alter table public.weibo_notes
    alter column created_at set default now();

update public.weibo_notes
set created_at = to_timestamp(last_modify_ts / 1000.0)
where created_at is not null
  and post_date is not null
  and created_at = post_date
  and last_modify_ts is not null
  and last_modify_ts > 0;
