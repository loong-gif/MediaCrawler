begin;

set local search_path = public;

delete from public.weibo_images stale
using public.weibo_images newer
where stale.note_id = newer.note_id
  and stale.image_index = newer.image_index
  and stale.id < newer.id;

create index if not exists idx_weibo_images_note_id
    on public.weibo_images (note_id);

create unique index if not exists idx_weibo_images_note_id_image_index
    on public.weibo_images (note_id, image_index);

commit;
