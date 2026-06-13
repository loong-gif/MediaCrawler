begin;

alter table if exists public.weibo_images
    add column if not exists is_selfie boolean;

commit;
