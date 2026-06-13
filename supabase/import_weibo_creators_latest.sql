begin;

set local search_path = public;

insert into public.weibo_creators (user_id, nickname, gender, avatar, "desc", ip_location, follows, fans, tag_list, last_modify_ts)
values
    (1149714543, '数码科技大搜索', '男', 'https://wx3.sinaimg.cn/orj480/4487406fly8gh3elgbqw2j20ro0roabw.jpg', '低调的人', NULL, 347, '14.6万', NULL, 1780452624700),
    (1350995007, '我是娜扎', '女', 'https://wx1.sinaimg.cn/orj480/001tqDw3ly8ida4tbukgkj60u00u0di102.jpg', NULL, NULL, 586, '2297.2万', NULL, 1780452676787),
    (1353112775, '张子枫', '女', 'https://wx1.sinaimg.cn/orj480/50a6dcc7ly8g4n2kl3qiwj20kv0kvjux.jpg', NULL, NULL, 507, '1498.8万', NULL, 1780452531576),
    (1669879400, 'Dear-迪丽热巴', '女', 'https://wx1.sinaimg.cn/orj480/63885668ly8geyrcrw0zjj20u00u0mz6.jpg', '一只喜欢默默表演的小透明。工作联系jaywalk@jaywalk.com.cn 🍒', NULL, 293, '8238.5万', NULL, 1780452698260),
    (1705586121, 'GEM鄧紫棋', '男', 'https://wx3.sinaimg.cn/orj480/001RqsRzly8h48mto22vtj60e80e8mxk02.jpg', '凡事包容，凡事相信，凡事盼望，凡事忍耐。愛是永不止息。', NULL, 507, '3588.8万', NULL, 1780452582131),
    (1713031610, '金晨', '女', 'https://wx4.sinaimg.cn/orj480/001RVHM6ly8ibic3ws8kyj60ez0ezjs002.jpg', NULL, NULL, 488, '1517.7万', NULL, 1780452646016),
    (1742568455, 'YIWWWWEN', '女', 'https://wx1.sinaimg.cn/orj480/67dd7c07ly8ge4xkt5whuj20u00u075v.jpg', '各平台同名（微博&amp;B站&amp;小🍠）', NULL, 105, '31.7万', NULL, 1780452438468),
    (2106192855, '赵今麦angel', '女', 'https://wx3.sinaimg.cn/orj480/7d89f3d7ly8id8rv4k72cj20u00u0q9g.jpg', '演员', NULL, 323, '1281.3万', NULL, 1780452709022),
    (2137467973, '裤KU', '女', 'https://wx1.sinaimg.cn/orj480/7f672c45ly8gl34leqhzcj20e80e8wes.jpg', 'Ku的美照bot', NULL, 224, '8763', NULL, 1780452428234),
    (2178928074, '演员任敏', '女', 'https://wx1.sinaimg.cn/orj480/81dfcdcaly8hfe7bjnvb2j20u00u0mzv.jpg', '工作合作邮箱：renmin@ewang.com', NULL, 211, '597.3万', NULL, 1780452655988),
    (2440179153, '宋祖儿lareina', '女', 'https://wx1.sinaimg.cn/orj480/91722dd1ly8gdjtgbo0ydj20e80e8jry.jpg', NULL, NULL, 196, '1650.5万', NULL, 1780452741093),
    (2449552120, '王玉雯Uvin', '女', 'https://wx2.sinaimg.cn/orj480/920132f8ly8i1wejek2idj20e80e8t9o.jpg', '工作联系 wywstudio@yeah.net', NULL, 345, '692.3万', NULL, 1780452687646),
    (2607803303, '章若楠', '女', 'https://wx1.sinaimg.cn/orj480/9b6feba7ly8id3nit6xa5j20u00u0wha.jpg', '有一个姑娘她有一些任性她还有一些嚣张。', NULL, 185, '1617.4万', NULL, 1779762139364),
    (2616380702, '白鹿my', '女', 'https://wx1.sinaimg.cn/orj480/002R448Kly8idoyf46i3sj60u00u0n1k02.jpg', '联系方式：bailubd@huanyuent.com', NULL, 450, '3152.5万', NULL, 1780452521146),
    (2731935637, '田曦薇', '女', 'https://wx4.sinaimg.cn/orj480/a2d60795ly8ictm12ntu1j20u00u0404.jpg', '🧱💪🏻工作联系:tianxiwei@haohanxingyuan.com', NULL, 355, '1313.5万', NULL, 1780452511094),
    (3477715953, '-Ovv_', '女', 'https://wx3.sinaimg.cn/orj480/cf49bbf1ly8gtmbu13t6wj20u00u0t9m.jpg', 'dy/xhs：vv', NULL, 99, '20.9万', NULL, 1780452635583),
    (3669102477, '鞠婧祎', '女', 'https://wx2.sinaimg.cn/orj480/0040jbadly8icq3if7twwj60qy0qy0uc02.jpg', NULL, NULL, 165, '3407.8万', NULL, 1780452751781),
    (3853697130, 'auntsteph', '女', 'https://wx2.sinaimg.cn/orj480/e5b2c06aly8fzp7j5qf9bj20e80e8q3q.jpg', '我喜欢橘子🍊  合作wx：auntsteph', NULL, 137, '133.9万', NULL, 1780452479313),
    (3932588380, '刘浩存', '女', 'https://wx1.sinaimg.cn/orj480/ea66895cly8id0hwzy29gj20rs0rsn2g.jpg', '工作请联系杨女士：lhcstudio@sina.com', NULL, 126, '619.8万', NULL, 1780452500194),
    (5124641655, '淘气雪蕊', '女', 'https://wx2.sinaimg.cn/orj480/005AOtozly8i7ow63qpz4j30nl0nlabf.jpg', NULL, NULL, 19, '37.4万', NULL, 1780452729539),
    (5292770234, 'Enndme', '女', 'https://wx2.sinaimg.cn/orj480/005MbVjQly8gjgvqk47gxj30e80e874r.jpg', '图片仅供参考 一切以本人为准', NULL, 256, '144.2万', NULL, 1780452418047),
    (5331040243, '沈月', '女', 'https://wx3.sinaimg.cn/orj480/005OMv63ly8i1obhxagprj30sz0sz76q.jpg', '˙Ꙫ˙', NULL, 364, '1526.1万', NULL, 1780452541473),
    (5372502779, '双下巴真可爱', '女', 'https://wx4.sinaimg.cn/orj480/005RAtoDly8h0znxlagfej30u00u0mxx.jpg', '谢谢喜欢', NULL, 289, '148.2万', NULL, 1780452375685),
    (5417332149, '是超级小蛋糕呀', '女', 'https://wx1.sinaimg.cn/orj480/005UCzyZly8hkawh6cy9tj30e80e83zg.jpg', '巧者劳而智者忧，无能者无所求。', NULL, 124, '5787', NULL, 1780452459214),
    (5503575607, '卢昱晓_', '女', 'https://wx1.sinaimg.cn/orj480/0060srqvly8icfj44c3fyj30u00u0q4w.jpg', '醉花宜昼，醉雪宜夜。', NULL, 376, '852.4万', NULL, 1780452665984),
    (5596373316, '卢远_Yuan', '女', 'https://wx1.sinaimg.cn/orj480/0066JOlKly8i31ayhgymzj30tx0txtau.jpg', NULL, NULL, 198, '32.8万', NULL, 1780452562120),
    (5598574734, '单依纯', '女', 'https://wx2.sinaimg.cn/orj480/0066T32uly8ibn1acuc7aj30u00u0wgs.jpg', NULL, NULL, 215, '1115.3万', NULL, 1780452592247),
    (5680343342, 'SNH48-费沁源--', '女', 'https://wx2.sinaimg.cn/orj480/006cq8N0ly8gxdtk29igdj30e80e8aag.jpg', '合作联系，商务：business@snh48.com 021-66075351 影视：yingshi@snh48.com 021-66078718*819 综艺：zongyi@snh48.com 021-66078718*821', NULL, 324, '439.3万', NULL, 1780452386508),
    (5749071359, 'L狸耳', '男', 'https://wx2.sinaimg.cn/orj480/006h4w5ply8hrmk0lrifoj30u00u0tb1.jpg', '所见即是我，好与坏不反驳 🫘🎵🍠狸耳 📮1973638722@qq.com', NULL, 200, '22.7万', NULL, 1780452572083),
    (5756404150, '英雄联盟赛事', 'Male', 'https://wx3.sinaimg.cn/orj480/006hzhGely8i8wt7myc5mj30u00u0ac4.jpg', '新岁启章，篇序更替，1月14日~2月6日，2026LPL第一赛段常规赛组内赛热血启程，无畏竞巅峰！', NULL, 621, '1144.6万', NULL, 1769678139303),
    (5936171972, '魔王小黄饱饱', '女', 'https://wx4.sinaimg.cn/orj480/006tJzvely8hdze08dtdsj30ks0ks3zk.jpg', '我的废话基地^部分仅粉可见', NULL, 335, '3774', NULL, 1780452489730),
    (5978764601, '又双叒叕想改名字了', '女', 'https://wx3.sinaimg.cn/orj480/006wChN7ly8guhedtv8t3j60ro0roacq02.jpg', '不完美 不较真 不怂', NULL, 101, '1927', NULL, 1780452469227),
    (5996184614, '微博轻享版小助理', '女', 'https://wx2.sinaimg.cn/orj480/006xNnx4ly8h8v3w28aspj30e80e8wel.jpg', '微博国际版官方客服→_→ 关注我，不迷路！', NULL, 31, '3060.9万', NULL, 1780452613915),
    (6011499980, '暴躁香奈鹅', '女', 'https://wx3.sinaimg.cn/orj480/006yPDL6ly8hyp0iedqh9j30u00u00uh.jpg', '凡事发生皆有利于我', NULL, 221, '3.6万', NULL, 1780452551977),
    (6124633386, '小罗爱芋泥鸭', '女', 'https://wx4.sinaimg.cn/orj480/006GukVsly8i9ahrjeisdj30u00u0js0.jpg', '小📕：小萝卜🐰 dy：小萝卜🐰', NULL, 87, '1010', NULL, 1780452448892),
    (6634214154, '宋雨琦_i-dle', '女', 'https://wx2.sinaimg.cn/orj480/007eYua6ly8i5ee5kdccgj30u00u00xh.jpg', '工作事宜请联系：contact_yuqi@163.com', NULL, 107, '1216万', NULL, 1780452603095),
    (7564215987, '椰汁太可爱了', '女', 'https://wx4.sinaimg.cn/orj480/008fUG7Fly8gnl34eudyvj30n10n10tf.jpg', NULL, NULL, 35, '1649', NULL, 1780452397022),
    (7746040822, 'VV宝贝a', '女', 'https://wx4.sinaimg.cn/orj480/008sdB4ily8h0a988ccl5j30fr0frabj.jpg', '平安喜乐 幸福安康 没有恋爱交友软件  不要被骗哦', NULL, 76, '12.6万', NULL, 1780452407740),
    (7930404930, '夏天心同学', '女', 'https://wx1.sinaimg.cn/orj480/008EHaAWly8hrllbjl78oj30e80e83yx.jpg', '哈哈ଘ៸៸᳐⦁⩊⦁៸៸᳐ଓ', NULL, 42, '5.8万', NULL, 1780452719398)
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
