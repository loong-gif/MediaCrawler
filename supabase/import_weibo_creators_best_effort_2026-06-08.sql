begin;

set local search_path = public;

insert into public.weibo_creators (user_id, nickname, gender, avatar, "desc", ip_location, follows, fans, tag_list, last_modify_ts)
values
    (5503575607, '卢昱晓_', '女', 'https://wx3.sinaimg.cn/orj480/0060srqvly8i91brl7c1vj30u00u0ad8.jpg', '醉花宜昼，醉雪宜夜。', NULL, 374, '843.4万', NULL, 1773073730574),
    (5372556014, '李一桐Q', '女', 'https://wx3.sinaimg.cn/orj480/005RAHfgly8i8fl1j5oynj60u00u0q5t02.jpg', '项目合作：jeanzen0612@163.com 宣传合作：330719936@qq.com 商务合作：Norbu0713@163.com', NULL, 191, '1924.4万', NULL, 1780909193255),
    (2731935637, '田曦薇', '女', 'https://wx2.sinaimg.cn/orj480/a2d60795ly8iaxap5k8rtj20rs0rsq4q.jpg', '🧱💪🏻工作联系:tianxiwei@haohanxingyuan.com', NULL, 350, '1190.1万', NULL, 1773073337502),
    (2607803303, '章若楠', '女', 'https://wx3.sinaimg.cn/orj480/9b6feba7ly8idwu9uvqtpj20sg0sgq4e.jpg', '有一个姑娘她有一些任性她还有一些嚣张。', NULL, 185, '1618.7万', NULL, 1780911584634),
    (2106192855, '赵今麦angel', '女', 'https://wx2.sinaimg.cn/orj480/7d89f3d7ly8grvykwc1w9j20e80e8dg7.jpg', '演员', NULL, 323, '1278.9万', NULL, 1773073878414)
on conflict (user_id) do update
set
    nickname = excluded.nickname,
    gender = excluded.gender,
    avatar = excluded.avatar,
    "desc" = excluded."desc",
    ip_location = excluded.ip_location,
    follows = excluded.follows,
    fans = excluded.fans,
    tag_list = excluded.tag_list,
    last_modify_ts = excluded.last_modify_ts
where excluded.last_modify_ts >= public.weibo_creators.last_modify_ts;

commit;
