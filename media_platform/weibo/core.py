# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/23 15:41
# @Desc    : 微博爬虫主流程代码

import asyncio
import os
# import random  # Removed as we now use fixed config.CRAWLER_MAX_SLEEP_SEC intervals
from asyncio import Task
from typing import Dict, List, Optional, Tuple

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import weibo as weibo_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var
from tqdm import tqdm

from .client import WeiboClient
from .exception import DataFetchError
from .field import SearchType
from .help import filter_search_result_card
from .login import WeiboLogin
from tools.observability import tracer as otel_tracer


class WeiboCrawler(AbstractCrawler):
    context_page: Page
    wb_client: WeiboClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self):
        self.index_url = "https://www.weibo.com"
        self.mobile_index_url = "https://m.weibo.cn"
        self.user_agent = utils.get_user_agent()
        self.mobile_user_agent = utils.get_mobile_user_agent()
        self.cdp_manager = None

    async def start(self):
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # 根据配置选择启动模式
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[WeiboCrawler] 使用CDP模式启动浏览器")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.mobile_user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[WeiboCrawler] 使用标准模式启动浏览器")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(chromium, None, self.mobile_user_agent, headless=config.HEADLESS)
            # 外部 CDP 浏览器（如 Lightpanda）对这份 stealth 脚本兼容性较差，
            # 注入后可能直接导致目标页崩溃，因此仅在非外部 CDP 模式下注入。
            if not config.CDP_REMOTE_WS_URL.strip():
                await self.browser_context.add_init_script(path="libs/stealth.min.js")
            self.context_page = await self.browser_context.new_page()
            try:
                await self.context_page.goto(self.mobile_index_url, wait_until="domcontentloaded", timeout=15000)
            except PlaywrightTimeoutError as ex:
                utils.logger.warning(
                    f"[WeiboCrawler.start] open mobile homepage timed out, continue with current session: {ex}"
                )

            # Create a client to interact with the xiaohongshu website.
            self.wb_client = await self.create_weibo_client(httpx_proxy_format)
            if not await self.wb_client.pong():
                login_obj = WeiboLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()

                # 登录成功后重定向到手机端的网站，再更新手机端登录成功的cookie
                utils.logger.info("[WeiboCrawler.start] redirect weibo mobile homepage and update cookies on mobile platform")
                await self.context_page.goto(self.mobile_index_url)
                await asyncio.sleep(2)
                await self.wb_client.update_cookies(browser_context=self.browser_context)

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for video and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            else:
                pass
            utils.logger.info("[WeiboCrawler.start] Weibo Crawler finished ...")

    async def search(self):
        """
        search weibo note with keywords
        :return:
        """
        with otel_tracer.start_as_current_span("weibo.search", attributes={"crawler.type": "search"}) as span:
            span.set_attribute("keywords", config.KEYWORDS)
            utils.logger.info("[WeiboCrawler.search] Begin search weibo keywords")
        weibo_limit_count = 10  # weibo limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < weibo_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = weibo_limit_count
        start_page = config.START_PAGE

        # Set the search type based on the configuration for weibo
        if config.WEIBO_SEARCH_TYPE == "default":
            search_type = SearchType.DEFAULT
        elif config.WEIBO_SEARCH_TYPE == "real_time":
            search_type = SearchType.REAL_TIME
        elif config.WEIBO_SEARCH_TYPE == "popular":
            search_type = SearchType.POPULAR
        elif config.WEIBO_SEARCH_TYPE == "video":
            search_type = SearchType.VIDEO
        else:
            utils.logger.error(f"[WeiboCrawler.search] Invalid WEIBO_SEARCH_TYPE: {config.WEIBO_SEARCH_TYPE}")
            return

        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[WeiboCrawler.search] Current search keyword: {keyword}")
            page = 1
            while (page - start_page + 1) * weibo_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[WeiboCrawler.search] Skip page: {page}")
                    page += 1
                    continue
                utils.logger.info(f"[WeiboCrawler.search] search weibo keyword: {keyword}, page: {page}")
                search_res = await self.wb_client.get_note_by_keyword(keyword=keyword, page=page, search_type=search_type)
                note_id_list: List[str] = []
                note_list = filter_search_result_card(search_res.get("cards"))
                for note_item in note_list:
                    if note_item:
                        mblog: Dict = note_item.get("mblog")
                        if mblog:
                            note_id_list.append(mblog.get("id"))
                            await weibo_store.update_weibo_note(note_item)
                            await self.get_note_images(mblog)

                page += 1
                
                # Sleep after page navigation
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[WeiboCrawler.search] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after page {page-1}")
                
                await self.batch_get_notes_comments(note_id_list)

    async def get_specified_notes(self):
        """
        get specified notes info
        :return:
        """
        with otel_tracer.start_as_current_span("weibo.get_specified_notes", attributes={"crawler.type": "detail"}):
            semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [self.get_note_info_task(note_id=note_id, semaphore=semaphore) for note_id in config.WEIBO_SPECIFIED_ID_LIST]
        video_details = await asyncio.gather(*task_list)
        for note_item in video_details:
            if note_item:
                await weibo_store.update_weibo_note(note_item)
        await self.batch_get_notes_comments(config.WEIBO_SPECIFIED_ID_LIST)

    async def get_note_info_task(self, note_id: str, semaphore: asyncio.Semaphore) -> Optional[Dict]:
        """
        Get note detail task
        :param note_id:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                result = await self.wb_client.get_note_info_by_id(note_id)
                
                # Sleep after fetching note details
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[WeiboCrawler.get_note_info_task] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching note details {note_id}")
                
                return result
            except DataFetchError as ex:
                utils.logger.error(f"[WeiboCrawler.get_note_info_task] Get note detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(f"[WeiboCrawler.get_note_info_task] have not fund note detail note_id:{note_id}, err: {ex}")
                return None

    async def batch_get_notes_comments(self, note_id_list: List[str]):
        """
        batch get notes comments
        :param note_id_list:
        :return:
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[WeiboCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
            return

        utils.logger.info(f"[WeiboCrawler.batch_get_notes_comments] note ids:{note_id_list}")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for note_id in note_id_list:
            task = asyncio.create_task(self.get_note_comments(note_id, semaphore), name=note_id)
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_note_comments(self, note_id: str, semaphore: asyncio.Semaphore):
        """
        get comment for note id
        :param note_id:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                utils.logger.info(f"[WeiboCrawler.get_note_comments] begin get note_id: {note_id} comments ...")
                
                # Sleep before fetching comments
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[WeiboCrawler.get_note_comments] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds before fetching comments for note {note_id}")
                
                await self.wb_client.get_note_all_comments(
                    note_id=note_id,
                    crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,  # Use fixed interval instead of random
                    callback=weibo_store.batch_update_weibo_note_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except DataFetchError as ex:
                utils.logger.error(f"[WeiboCrawler.get_note_comments] get note_id: {note_id} comment error: {ex}")
            except Exception as e:
                utils.logger.error(f"[WeiboCrawler.get_note_comments] may be been blocked, err:{e}")

    async def get_note_images(self, mblog: Dict):
        """
        get note images
        :param mblog:
        :return:
        """
        if not config.ENABLE_GET_MEIDAS:
            utils.logger.info(f"[WeiboCrawler.get_note_images] Crawling image mode is not enabled")
            return

        pics: Dict = mblog.get("pics")
        if not pics:
            return
        for pic in pics:
            url = pic.get("url")
            if not url:
                continue
            content = await self.wb_client.get_note_image(url)
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
            utils.logger.info(f"[WeiboCrawler.get_note_images] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching image")
            if content != None:
                extension_file_name = url.split(".")[-1]
                await weibo_store.update_weibo_note_image(pic["pid"], content, extension_file_name)

    async def get_creators_and_notes(self) -> None:
        """
        Get creator's information and their notes and comments
        Returns:

        """
        with otel_tracer.start_as_current_span("weibo.get_creators_and_notes", attributes={"crawler.type": "creator"}):
            utils.logger.info("[WeiboCrawler.get_creators_and_notes] Begin get weibo creators")
        creator_total = len(config.WEIBO_CREATOR_ID_LIST)
        summary = {
            "success": 0,
            "skip": 0,
            "fail": 0,
            "notes": 0,
        }
        with tqdm(total=creator_total, desc="Weibo creators", unit="creator") as progress:
            for user_id in config.WEIBO_CREATOR_ID_LIST:
                creator_saved = False
                progress.set_postfix(
                    {
                        "id": user_id,
                        "ok": summary["success"],
                        "skip": summary["skip"],
                        "fail": summary["fail"],
                        "notes": summary["notes"],
                    },
                    refresh=False,
                )
                utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] progress {progress.n + 1}/{creator_total}, creator_id:{user_id}")
                try:
                    createor_info_res: Dict = await self.wb_client.get_creator_info_by_id(creator_id=user_id)
                    if not createor_info_res:
                        utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] get creator info error, creator_id:{user_id}")
                        summary["fail"] += 1
                        continue

                    createor_info: Dict = createor_info_res.get("userInfo", {})
                    utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] creator info: {createor_info}")
                    if not createor_info:
                        utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] empty creator info, creator_id:{user_id}")
                        summary["skip"] += 1
                        continue

                    creator_name = (
                        createor_info.get("screen_name")
                        or createor_info.get("name")
                        or createor_info.get("screen_name_suffix")
                        or user_id
                    )

                    await weibo_store.save_creator(user_id, user_info=createor_info)
                    creator_saved = True

                    # 在获取 creator 信息后，开始获取笔记列表前增加延迟，避免连续请求触发反爬虫
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                    utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] 等待 {config.CRAWLER_MAX_SLEEP_SEC} 秒后开始获取用户 {user_id} 的笔记列表")

                    # Get all note information of the creator
                    all_notes_list = await self.wb_client.get_all_notes_by_creator_id(
                        creator_id=user_id,
                        container_id=createor_info_res.get("lfid_container_id"),
                        crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,  # 使用配置的延迟时间，降低触发反爬虫的概率
                        callback=weibo_store.batch_update_weibo_notes,
                        progress_callback=lambda status, p=progress: p.set_postfix(
                            {
                                "name": creator_name[:12],
                                "ok": summary["success"],
                                "skip": summary["skip"],
                                "fail": summary["fail"],
                                "notes": summary["notes"],
                                "page": status.get("page"),
                                "page_notes": status.get("page_notes"),
                                "total_notes": status.get("notes_total"),
                            },
                            refresh=True,
                        ),
                        max_retries=5,  # 增加重试次数（默认3次）
                        retry_delay=10.0,  # 增加重试延迟（默认5秒，改为10秒）
                    )

                    note_ids = [note_item.get("mblog", {}).get("id") for note_item in all_notes_list if note_item.get("mblog", {}).get("id")]
                    summary["notes"] += len(note_ids)
                    if note_ids:
                        utils.logger.info(
                            f"[WeiboCrawler.get_creators_and_notes] creator_id={user_id} 本轮获取 {len(note_ids)} 条微博，按成功计入汇总"
                        )
                        summary["success"] += 1
                    else:
                        utils.logger.warning(
                            f"[WeiboCrawler.get_creators_and_notes] creator_id={user_id} 已获取创作者资料，但微博结果为空，按 skip 计入汇总。"
                            f" lfid_container_id={createor_info_res.get('lfid_container_id')}, "
                            f"fid_container_id={createor_info_res.get('fid_container_id')}, "
                            f"raw_notes={len(all_notes_list)}"
                        )
                        summary["skip"] += 1
                    progress.set_postfix(
                        {
                            "name": creator_name[:12],
                            "ok": summary["success"],
                            "skip": summary["skip"],
                            "fail": summary["fail"],
                            "notes": summary["notes"],
                        },
                        refresh=True,
                    )
                    await self.batch_get_notes_comments(note_ids)
                except DataFetchError as ex:
                    if creator_saved:
                        utils.logger.warning(
                            f"[WeiboCrawler.get_creators_and_notes] creator_id={user_id} 资料已保存，但微博抓取中断，按 skip 计入汇总，err:{ex}"
                        )
                        summary["skip"] += 1
                    else:
                        utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] creator fetch failed, creator_id:{user_id}, err:{ex}")
                        summary["fail"] += 1
                except Exception as ex:
                    utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] unexpected error, creator_id:{user_id}, err:{ex}")
                    summary["fail"] += 1
                finally:
                    progress.update(1)
                    progress.set_postfix(
                        {
                            "ok": summary["success"],
                            "skip": summary["skip"],
                            "fail": summary["fail"],
                            "notes": summary["notes"],
                        },
                        refresh=False,
                    )
        utils.logger.info(
            f"[WeiboCrawler.get_creators_and_notes] summary success={summary['success']}, skip={summary['skip']}, fail={summary['fail']}, notes={summary['notes']}"
        )

    async def create_weibo_client(self, httpx_proxy: Optional[str]) -> WeiboClient:
        """Create xhs client"""
        utils.logger.info("[WeiboCrawler.create_weibo_client] Begin create weibo API client ...")
        browser_cookie_str, browser_cookie_dict = utils.convert_cookies(await self.browser_context.cookies())
        config_cookie_str = config.COOKIES.strip()
        has_browser_auth_cookie = bool(browser_cookie_dict.get("SUB") and browser_cookie_dict.get("SUBP"))
        # 显式 cookie 登录时，优先使用配置里的 Cookie，会话来源更可控。
        if config.LOGIN_TYPE == "cookie" and config_cookie_str:
            cookie_str = config_cookie_str
            cookie_source = "config"
        # 其他模式下，CDP 优先使用浏览器当前登录态，避免静态配置 Cookie 覆盖掉已过风控/验证码的会话。
        elif config.ENABLE_CDP_MODE and browser_cookie_str.strip() and has_browser_auth_cookie:
            cookie_str = browser_cookie_str
            cookie_source = "browser"
        else:
            cookie_str = config_cookie_str or browser_cookie_str
            cookie_source = "config" if config_cookie_str else "browser"
        cookie_dict = browser_cookie_dict

        utils.logger.info(
            f"[WeiboCrawler.create_weibo_client] browser_cookie_count={len(browser_cookie_dict)}, "
            f"config_cookie_len={len(config_cookie_str)}, has_browser_auth_cookie={has_browser_auth_cookie}, "
            f"cookie_source={cookie_source}"
        )
        
        # 使用更完整的请求头，模拟真实浏览器，降低触发 432 风控的概率
        user_agent = utils.get_mobile_user_agent()
        weibo_client_obj = WeiboClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": user_agent,
                "Cookie": cookie_str,
                "Origin": "https://m.weibo.cn",
                "Referer": "https://m.weibo.cn",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/json;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return weibo_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info("[WeiboCrawler.launch_browser] Begin create browser context ...")
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                user_agent=user_agent,
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=user_agent)
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        使用CDP模式启动浏览器
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # 显示浏览器信息
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[WeiboCrawler] CDP浏览器信息: {browser_info}")

            return browser_context

        except Exception as e:
            if config.CDP_REMOTE_WS_URL.strip():
                utils.logger.error(f"[WeiboCrawler] 外部CDP模式启动失败，终止本次运行: {e}")
                raise
            utils.logger.error(f"[WeiboCrawler] CDP模式启动失败，回退到标准模式: {e}")
            # 回退到标准模式
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def close(self):
        """Close browser context"""
        # 如果使用CDP模式，需要特殊处理
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[WeiboCrawler.close] Browser context closed ...")
