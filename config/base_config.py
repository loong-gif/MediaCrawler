# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

# 基础配置
PLATFORM = "wb"  # 平台，xhs | dy | ks | bili | wb | tieba | zhihu
KEYWORDS = "编程副业,编程兼职"  # 关键词搜索配置，以英文逗号分隔
LOGIN_TYPE = "cookie"  # qrcode or phone or cookie
COOKIES = "SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WhEsl8SouY2Us7cEWVLgRau5NHD95QReh2XehqcShBcWs4Dqcj7qg8yi--ci-z4iK.ci--fiKy2iK.Ni--fi-2Ei-2Ri--4i-iWiK.Ei--4i-iWiKLs; netease_token=3cc3bf8c78331fd5a0e0e6d993de5653; SUB=_2A25HLEbsDeRhGe5O6lYR9ijIzzqIHXVkQMYkrDV6PUJbktAbLUXtkW1NdZANMHn7oO2atplGruXwmsq-jQEcOzLC; ALF=1783612348; SCF=Ap4R_r_86VNGQdyTQs0bm0T9F1lZVMYZwu6j_SmZF6xB5owIKvKs5G0TYulBmsJ1dubOWBromCCVWb4O-pTD4_U.; SSOLoginState=1781020348"
CRAWLER_TYPE = (
    "creator"  # 爬取类型，search(关键词搜索) | detail(帖子详情)| creator(创作者主页数据)
)
# 是否开启 IP 代理
ENABLE_IP_PROXY = False

# 代理IP池数量
IP_PROXY_POOL_COUNT = 2

# 代理IP提供商名称
IP_PROXY_PROVIDER_NAME = "kuaidaili"  # kuaidaili | wandouhttp

# 设置为True不会打开浏览器（无头浏览器）
# 设置False会打开一个浏览器
# 小红书如果一直扫码登录不通过，打开浏览器手动过一下滑动验证码
# 抖音如果一直提示失败，打开浏览器看下是否扫码登录之后出现了手机号验证，如果出现了手动过一下再试。
HEADLESS = True

# 是否保存登录状态
SAVE_LOGIN_STATE = True

# ==================== CDP (Chrome DevTools Protocol) 配置 ====================
# 是否启用CDP模式 - 使用用户现有的Chrome/Edge浏览器进行爬取，提供更好的反检测能力
# 启用后将自动检测并启动用户的Chrome/Edge浏览器，通过CDP协议进行控制
# 这种方式使用真实的浏览器环境，包括用户的扩展、Cookie和设置，大大降低被检测的风险
ENABLE_CDP_MODE = True

import os

# 外部CDP地址。
# 为空时保持原有行为：由项目自己启动 Chrome/Edge 再连接。
# Lightpanda 或其他兼容 CDP 的浏览器可填写类似 ws://127.0.0.1:9222/ 的地址。
CDP_REMOTE_WS_URL = os.getenv("CDP_REMOTE_WS_URL", "").strip()

# CDP模式下是否启用无头模式
# 注意：即使设置为True，某些反检测功能在无头模式下可能效果不佳
CDP_HEADLESS = False

# 浏览器启动超时时间（秒）
BROWSER_LAUNCH_TIMEOUT = 30

# 是否在程序结束时自动关闭浏览器
# 设置为False可以保持浏览器运行，便于调试
AUTO_CLOSE_BROWSER = False

# 自定义浏览器路径（可选）
# 如果为空，系统会自动检测Chrome/Edge的安装路径
# Windows示例: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# macOS示例: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CUSTOM_BROWSER_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# CDP模式下是否启用无头模式
# 注意：即使设置为True，某些反检测功能在无头模式下可能效果不佳
CDP_HEADLESS = False

# 浏览器启动超时时间（秒）
BROWSER_LAUNCH_TIMEOUT = 30

# 是否在程序结束时自动关闭浏览器
# 设置为False可以保持浏览器运行，便于调试
AUTO_CLOSE_BROWSER = True

# 数据保存类型选项配置。
# supabase 为微博专用的 Supabase Postgres 直连模式，需要配置 SUPABASE_DB_URL
# 或 SUPABASE_DB_HOST / SUPABASE_DB_USER / SUPABASE_DB_PWD / SUPABASE_DB_NAME。
SAVE_DATA_OPTION = "csv"  # csv or db or json or sqlite or supabase

# 文件输出目录配置（csv/json）
# 设置为绝对路径后，文件将写入该目录下
FILE_OUTPUT_ROOT = "/Volumes/人脸识别数据集"
# 是否按日期自动创建子目录（例如 /Volumes/人脸识别数据集/2026-03-06/...）
FILE_OUTPUT_USE_DATE_DIR = True

# 用户浏览器缓存的浏览器文件配置
USER_DATA_DIR = "%s_user_data_dir"  # %s will be replaced by platform name

# 爬取开始页数 默认从第一页开始
START_PAGE = 1

# 微博创作者主页抓取截止日期
# 为空时默认只抓取最近 7 天；填写 YYYY-MM-DD 或 ISO8601 时间字符串后，会抓取该时间之后的帖子
WEIBO_CREATOR_SINCE_DATE = ""

# 爬取视频/帖子的数量控制
CRAWLER_MAX_NOTES_COUNT = 5000

# 并发爬虫数量控制
MAX_CONCURRENCY_NUM = 1

# 是否开启爬媒体模式（包含图片或视频资源），默认不开启爬媒体
ENABLE_GET_MEIDAS = True

# 微博媒体下载过滤配置：
# all: 抓取到图片链接后立即下载（兼容现有行为）
# is_selfie_true: 仅当 weibo_images.is_selfie = TRUE 时下载
WEIBO_MEDIA_DOWNLOAD_FILTER = "is_selfie_true"

# 是否开启爬评论模式, 默认开启爬评论
ENABLE_GET_COMMENTS = False

# 爬取一级评论的数量控制(单视频/帖子)
CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 10

# 是否开启爬二级评论模式, 默认不开启爬二级评论
# 老版本项目使用了 db, 则需参考 schema/tables.sql line 287 增加表字段
ENABLE_GET_SUB_COMMENTS = False

# 词云相关
# 是否开启生成评论词云图
ENABLE_GET_WORDCLOUD = False
# 自定义词语及其分组
# 添加规则：xx:yy 其中xx为自定义添加的词组，yy为将xx该词组分到的组名。
CUSTOM_WORDS = {
    "零几": "年份",  # 将“零几”识别为一个整体
    "高频词": "专业术语",  # 示例自定义词
}

# 停用(禁用)词文件路径
STOP_WORDS_FILE = "./docs/hit_stopwords.txt"

# 中文字体文件路径
FONT_PATH = "./docs/STZHONGS.TTF"

# 爬取间隔时间（增加延迟以降低触发反爬虫的概率）
CRAWLER_MAX_SLEEP_SEC = 5

from .bilibili_config import *
from .xhs_config import *
from .dy_config import *
from .ks_config import *
from .weibo_config import *
from .tieba_config import *
from .zhihu_config import *
