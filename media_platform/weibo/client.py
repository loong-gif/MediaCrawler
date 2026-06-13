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
# @Time    : 2023/12/23 15:40
# @Desc    : 微博爬虫 API 请求 client

import asyncio
import copy
import json
import random
import re
from typing import Callable, Dict, List, Optional, Union
from urllib.parse import parse_qs, unquote, urlencode

import httpx
from httpx import Response
from playwright.async_api import BrowserContext, Page

import config
from tools import utils
import time
from datetime import datetime, timedelta, timezone

from .exception import DataFetchError
from .field import SearchType


class WeiboClient:

    def __init__(
        self,
        timeout=60,  # 若开启爬取媒体选项，weibo 的图片需要更久的超时时间
        proxy=None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers
        self._host = "https://m.weibo.cn"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._image_agent_host = "https://i1.wp.com/"

    async def request(self, method, url, **kwargs) -> Union[Response, Dict]:
        enable_return_response = kwargs.pop("return_response", False)
        follow_redirects = kwargs.pop("follow_redirects", True)  # 默认跟随重定向
        async with httpx.AsyncClient(proxy=self.proxy, follow_redirects=follow_redirects) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if enable_return_response:
            return response

        # 检查HTTP状态码
        if not (200 <= response.status_code < 300):
            # 特殊处理 302 重定向
            if response.status_code == 302:
                redirect_location = response.headers.get("Location", "")
                if "login" in redirect_location.lower() or "passport" in redirect_location.lower():
                    error_msg = "Cookie 可能已失效，需要重新登录。请检查 Cookie 是否有效。"
                    utils.logger.error(
                        f"[WeiboClient.request] {method} {url} 重定向到登录页面: {redirect_location}"
                    )
                else:
                    error_msg = f"HTTP 302 重定向错误，重定向到: {redirect_location}"
                    utils.logger.error(
                        f"[WeiboClient.request] {method} {url} 收到 302 重定向，Location: {redirect_location}"
                    )
            else:
                error_msg = f"HTTP {response.status_code} error"
                try:
                    error_text = response.text[:500]  # 只取前500个字符
                    utils.logger.error(
                        f"[WeiboClient.request] {method} {url} failed with status {response.status_code}, response: {error_text}"
                    )
                except Exception:
                    utils.logger.error(
                        f"[WeiboClient.request] {method} {url} failed with status {response.status_code}"
                    )
            raise DataFetchError(error_msg)

        # 检查响应内容是否为空
        if not response.text or not response.text.strip():
            utils.logger.error(f"[WeiboClient.request] {method} {url} returned empty response")
            raise DataFetchError("Empty response from server")

        # 尝试解析JSON
        try:
            data: Dict = response.json()
        except json.JSONDecodeError as e:
            error_text = response.text[:500]  # 只取前500个字符用于日志
            utils.logger.error(f"[WeiboClient.request] {method} {url} JSON decode error: {e}, response: {error_text}")
            raise DataFetchError(f"Invalid JSON response: {str(e)}")

        ok_code = data.get("ok")
        if ok_code == 0:  # response error
            error_msg = data.get("msg", "")
            error_type = data.get("error_type", "")
            errno = data.get("errno", "")
            extra = data.get("extra", "")
            
            # 构建详细的错误信息
            if error_msg:
                full_error_msg = error_msg
            else:
                full_error_msg = "response error"
            
            if errno:
                full_error_msg += f" (errno: {errno})"
            if error_type:
                full_error_msg += f" (type: {error_type})"
            if extra:
                # extra 可能是字符串，需要处理
                if isinstance(extra, str):
                    full_error_msg += f" (extra: {extra[:200]})"  # 限制长度
                else:
                    full_error_msg += f" (extra: {extra})"
            
            # 输出完整的响应数据用于调试
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err, full response: {data}")
            raise DataFetchError(full_error_msg)
        elif ok_code == -100:
            errno = data.get("errno", "")
            captcha_url = data.get("url", "")
            utils.logger.error(
                f"[WeiboClient.request] request {method}:{url} hit captcha challenge, errno={errno}, captcha_url={captcha_url}"
            )
            raise DataFetchError(f"captcha_required errno={errno} url={captcha_url}")
        elif ok_code != 1:  # unknown error
            errno = data.get("errno", "")
            error_msg = data.get("msg", "") or "unknown error"
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err, res:{data}")
            if errno:
                error_msg = f"{error_msg} (errno: {errno})"
            raise DataFetchError(error_msg)
        else:  # response right
            return data.get("data", {})

    async def get(self, uri: str, params=None, headers=None, **kwargs) -> Union[Response, Dict]:
        final_uri = uri
        if isinstance(params, dict):
            final_uri = (f"{uri}?"
                         f"{urlencode(params)}")

        if headers is None:
            headers = copy.copy(self.headers)  # 使用副本，避免修改原始 headers
        else:
            # 合并自定义 headers 和默认 headers，确保必要的请求头不会丢失
            merged_headers = copy.copy(self.headers)
            merged_headers.update(headers)
            headers = merged_headers
        
        # 确保 Referer 正确设置（如果未设置，使用默认值）
        if "Referer" not in headers or not headers.get("Referer"):
            headers["Referer"] = f"{self._host}{uri}" if not uri.startswith("http") else uri
        
        return await self.request(method="GET", url=f"{self._host}{final_uri}", headers=headers, **kwargs)

    async def post(self, uri: str, data: dict) -> Dict:
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return await self.request(method="POST", url=f"{self._host}{uri}", data=json_str, headers=self.headers)

    async def pong(self) -> bool:
        """get a note to check if login state is ok"""
        utils.logger.info("[WeiboClient.pong] Begin pong weibo...")
        ping_flag = False
        try:
            uri = "/api/config"
            resp_data: Dict = await self.request(method="GET", url=f"{self._host}{uri}", headers=self.headers)
            if resp_data.get("login"):
                ping_flag = True
            else:
                utils.logger.error(f"[WeiboClient.pong] cookie may be invalid and again login...")
        except Exception as e:
            utils.logger.error(f"[WeiboClient.pong] Pong weibo failed: {e}, and try to login again...")
            ping_flag = False
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext):
        cookie_str, cookie_dict = utils.convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def get_note_by_keyword(
        self,
        keyword: str,
        page: int = 1,
        search_type: SearchType = SearchType.DEFAULT,
    ) -> Dict:
        """
        search note by keyword
        :param keyword: 微博搜搜的关键词
        :param page: 分页参数 -当前页码
        :param search_type: 搜索的类型，见 weibo/filed.py 中的枚举SearchType
        :return:
        """
        uri = "/api/container/getIndex"
        containerid = f"100103type={search_type.value}&q={keyword}"
        params = {
            "containerid": containerid,
            "page_type": "searchall",
            "page": page,
        }
        return await self.get(uri, params)

    async def get_note_comments(self, mid_id: str, max_id: int, max_id_type: int = 0) -> Dict:
        """get notes comments
        :param mid_id: 微博ID
        :param max_id: 分页参数ID
        :param max_id_type: 分页参数ID类型
        :return:
        """
        # 验证 mid_id 格式：应该是数字字符串，长度在合理范围内（1-19位）
        if not mid_id or not mid_id.isdigit():
            raise DataFetchError(f"Invalid mid_id format: {mid_id}")
        
        # 检查 mid_id 是否超出 long 类型最大值（9223372036854775807，19位）
        if len(mid_id) > 19:
            utils.logger.warning(f"[WeiboClient.get_note_comments] mid_id too long ({len(mid_id)} digits), may be invalid: {mid_id}")
            # 尝试截取前19位（如果可能）
            if len(mid_id) <= 38:  # 可能是两个ID拼接
                # 尝试分割：如果长度是偶数，可能是两个ID拼接
                half_len = len(mid_id) // 2
                mid_id = mid_id[:half_len]  # 使用前半部分
                utils.logger.info(f"[WeiboClient.get_note_comments] Using first half of mid_id: {mid_id}")
            else:
                raise DataFetchError(f"mid_id too long and cannot be split: {mid_id}")
        
        uri = "/comments/hotflow"
        params = {
            "id": mid_id,
            "mid": mid_id,
            "max_id_type": max_id_type,
        }
        if max_id > 0:
            params.update({"max_id": max_id})
        referer_url = f"https://m.weibo.cn/detail/{mid_id}"
        headers = copy.copy(self.headers)
        headers["Referer"] = referer_url

        return await self.get(uri, params, headers=headers)

    async def get_note_all_comments(
        self,
        note_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ):
        """
        get note all comments include sub comments
        :param note_id:
        :param crawl_interval:
        :param callback:
        :param max_count:
        :return:
        """
        result = []
        is_end = False
        max_id = -1
        max_id_type = 0
        while not is_end and len(result) < max_count:
            comments_res = await self.get_note_comments(note_id, max_id, max_id_type)
            max_id: int = comments_res.get("max_id")
            max_id_type: int = comments_res.get("max_id_type")
            comment_list: List[Dict] = comments_res.get("data", [])
            is_end = max_id == 0
            if len(result) + len(comment_list) > max_count:
                comment_list = comment_list[:max_count - len(result)]
            if callback:  # 如果有回调函数，就执行回调函数
                await callback(note_id, comment_list)
            await asyncio.sleep(crawl_interval)
            result.extend(comment_list)
            sub_comment_result = await self.get_comments_all_sub_comments(note_id, comment_list, callback)
            result.extend(sub_comment_result)
        return result

    @staticmethod
    async def get_comments_all_sub_comments(
        note_id: str,
        comment_list: List[Dict],
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取评论的所有子评论
        Args:
            note_id:
            comment_list:
            callback:

        Returns:

        """
        if not config.ENABLE_GET_SUB_COMMENTS:
            utils.logger.info(f"[WeiboClient.get_comments_all_sub_comments] Crawling sub_comment mode is not enabled")
            return []

        res_sub_comments = []
        for comment in comment_list:
            sub_comments = comment.get("comments")
            if sub_comments and isinstance(sub_comments, list):
                await callback(note_id, sub_comments)
                res_sub_comments.extend(sub_comments)
        return res_sub_comments

    async def get_note_info_by_id(self, note_id: str, max_retries: int = 3, retry_delay: float = 5.0) -> Dict:
        """
        根据帖子ID获取详情
        :param note_id:
        :param max_retries: 最大重试次数（针对网络错误）
        :param retry_delay: 重试延迟（秒）
        :return:
        """
        url = f"{self._host}/detail/{note_id}"
        
        # 添加重试机制处理网络错误
        retry_count = 0
        response = None
        while retry_count <= max_retries:
            try:
                async with httpx.AsyncClient(proxy=self.proxy) as client:
                    response = await client.request("GET", url, timeout=self.timeout, headers=self.headers)
                    if response.status_code != 200:
                        raise DataFetchError(f"get weibo detail err: {response.text}")
                    break  # 成功获取响应，跳出重试循环
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = retry_delay * retry_count  # 指数退避
                    utils.logger.warning(
                        f"[WeiboClient.get_note_info_by_id] 网络错误 ({type(e).__name__})，"
                        f"等待 {wait_time} 秒后重试 ({retry_count}/{max_retries}), note_id: {note_id}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    utils.logger.error(
                        f"[WeiboClient.get_note_info_by_id] 达到最大重试次数 ({max_retries})，"
                        f"无法获取笔记详情, note_id: {note_id}, error: {e}"
                    )
                    raise DataFetchError(f"网络错误，无法获取笔记详情: {str(e)}")
            except Exception as e:
                # 其他错误直接抛出
                utils.logger.error(f"[WeiboClient.get_note_info_by_id] 获取笔记详情时发生未知错误, note_id: {note_id}, error: {e}")
                raise
        
        if not response:
            raise DataFetchError(f"无法获取响应, note_id: {note_id}")
        
        response_text = response.text
        
        # 尝试多种方式解析 render_data
        # 方式1: var $render_data = [...] [0]
        match = re.search(r'var \$render_data\s*=\s*(\[.*?\])\[0\]', response_text, re.DOTALL)
        if not match:
            # 方式2: $render_data = [...] [0] (没有var)
            match = re.search(r'\$render_data\s*=\s*(\[.*?\])\[0\]', response_text, re.DOTALL)
        if not match:
            # 方式3: render_data = {...} (对象格式)
            match = re.search(r'var \$render_data\s*=\s*(\{.*?\})', response_text, re.DOTALL)
        if not match:
            # 方式4: 查找 window.render_data 或其他变体
            match = re.search(r'window\.\$render_data\s*=\s*(\[.*?\])\[0\]', response_text, re.DOTALL)
        
        if match:
            try:
                render_data_json = match.group(1)
                render_data_dict = json.loads(render_data_json)
                
                # 处理数组格式
                if isinstance(render_data_dict, list) and len(render_data_dict) > 0:
                    note_detail = render_data_dict[0].get("status")
                # 处理对象格式
                elif isinstance(render_data_dict, dict):
                    note_detail = render_data_dict.get("status")
                else:
                    note_detail = None
                
                if note_detail:
                    note_item = {"mblog": note_detail}
                    return note_item
                else:
                    utils.logger.warning(f"[WeiboClient.get_note_info_by_id] 解析到render_data但未找到status字段, note_id: {note_id}")
            except json.JSONDecodeError as e:
                utils.logger.error(f"[WeiboClient.get_note_info_by_id] JSON解析失败, note_id: {note_id}, error: {e}")
            except Exception as e:
                utils.logger.error(f"[WeiboClient.get_note_info_by_id] 解析render_data时出错, note_id: {note_id}, error: {e}")
        
        # 如果所有方式都失败，输出调试信息
        utils.logger.warning(f"[WeiboClient.get_note_info_by_id] 未找到$render_data的值, note_id: {note_id}")
        # 输出响应内容的一部分用于调试（检查页面是否正常加载）
        if len(response_text) > 0:
            # 检查是否是重定向或错误页面
            if "登录" in response_text or "login" in response_text.lower():
                utils.logger.warning(f"[WeiboClient.get_note_info_by_id] 页面可能要求登录, note_id: {note_id}")
            elif "404" in response_text or "不存在" in response_text or "not found" in response_text.lower():
                utils.logger.warning(f"[WeiboClient.get_note_info_by_id] 笔记可能不存在或已删除, note_id: {note_id}")
            else:
                # 输出响应内容的前500个字符用于调试
                preview = response_text[:500].replace('\n', ' ').replace('\r', ' ')
                utils.logger.debug(f"[WeiboClient.get_note_info_by_id] 响应内容预览: {preview}...")
        
        return dict()

    async def get_note_image(self, image_url: str) -> bytes:
        image_url = image_url[8:]  # 去掉 https://
        sub_url = image_url.split("/")
        image_url = ""
        for i in range(len(sub_url)):
            if i == 1:
                image_url += "large/"  # 都获取高清大图
            elif i == len(sub_url) - 1:
                image_url += sub_url[i]
            else:
                image_url += sub_url[i] + "/"
        # 微博图床对外存在防盗链，所以需要代理访问
        # 由于微博图片是通过 i1.wp.com 来访问的，所以需要拼接一下
        final_uri = (f"{self._image_agent_host}"
                     f"{image_url}")
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            try:
                response = await client.request("GET", final_uri, timeout=self.timeout)
                response.raise_for_status()
                if not response.reason_phrase == "OK":
                    utils.logger.error(f"[WeiboClient.get_note_image] request {final_uri} err, res:{response.text}")
                    return None
                else:
                    return response.content
            except httpx.HTTPError as exc:  # some wrong when call httpx.request method, such as connection error, client error, server error or response status code is not 2xx
                utils.logger.error(f"[DouYinClient.get_aweme_media] {exc.__class__.__name__} for {exc.request.url} - {exc}")    # 保留原始异常类型名称，以便开发者调试
                return None

    async def get_creator_container_info(self, creator_id: str) -> Dict:
        """
        获取用户的容器ID, 容器信息代表着真实请求的API路径
            fid_container_id：用户的微博详情API的容器ID
            lfid_container_id：用户的微博列表API的容器ID
        Args:
            creator_id:

        Returns: {

        """
        response = await self.get(f"/u/{creator_id}", return_response=True)
        m_weibocn_params = response.cookies.get("M_WEIBOCN_PARAMS")
        
        # 如果 Cookie 中没有 M_WEIBOCN_PARAMS，尝试从响应内容中解析
        if not m_weibocn_params:
            utils.logger.warning(f"[WeiboClient.get_creator_container_info] Cookie 中没有 M_WEIBOCN_PARAMS，尝试从响应内容中解析")
            # 尝试从响应 HTML 中查找 containerid
            response_text = response.text if hasattr(response, 'text') else ""
            # 查找 containerid 的模式，例如：containerid=1005053669102477 或 containerid="1005053669102477"
            containerid_pattern = r'containerid["\']?\s*[:=]\s*["\']?(\d+)'
            matches = re.findall(containerid_pattern, response_text)
            if matches:
                # 使用第一个匹配的 containerid
                fid_container_id = matches[0]
                # 检查是否已经是完整格式（以 100505 开头），如果不是则添加前缀
                if not fid_container_id.startswith("100505"):
                    fid_container_id = f"100505{fid_container_id}"
                utils.logger.info(f"[WeiboClient.get_creator_container_info] 从响应内容中解析到 containerid: {fid_container_id}")
                # lfid_container_id 通常可以通过 API 获取，先返回空的
                return {"fid_container_id": fid_container_id, "lfid_container_id": ""}
            else:
                # 如果还是找不到，使用默认的 containerid 格式
                utils.logger.warning(f"[WeiboClient.get_creator_container_info] 无法从响应中解析 containerid，使用默认格式")
                return {"fid_container_id": f"100505{creator_id}", "lfid_container_id": ""}
        
        m_weibocn_params_dict = parse_qs(unquote(m_weibocn_params))
        return {"fid_container_id": m_weibocn_params_dict.get("fid", [""])[0], "lfid_container_id": m_weibocn_params_dict.get("lfid", [""])[0]}

    async def get_creator_info_by_id(self, creator_id: str) -> Dict:
        """
        根据用户ID获取用户详情
        Args:
            creator_id:

        Returns:

        """
        uri = "/api/container/getIndex"
        container_info = await self.get_creator_container_info(creator_id)
        
        # 如果 fid_container_id 为空，使用默认格式
        if not container_info.get("fid_container_id"):
            container_info["fid_container_id"] = f"100505{creator_id}"
            utils.logger.warning(f"[WeiboClient.get_creator_info_by_id] 使用默认 fid_container_id: {container_info['fid_container_id']}")
        
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator_id,
            "containerid": container_info["fid_container_id"],
        }

        user_res = await self.get(uri, params)

        # 从 API 响应中获取 lfid_container_id
        if user_res.get("tabsInfo"):
            tabs: List[Dict] = user_res.get("tabsInfo", {}).get("tabs", [])
            for tab in tabs:
                if tab.get("tabKey") == "weibo":
                    container_info["lfid_container_id"] = tab.get("containerid")
                    utils.logger.info(f"[WeiboClient.get_creator_info_by_id] 从 tabsInfo 中获取到 lfid_container_id: {container_info['lfid_container_id']}")
                    break
        
        # 如果还是没有 lfid_container_id，使用默认格式
        if not container_info.get("lfid_container_id"):
            container_info["lfid_container_id"] = f"107603{creator_id}"
            utils.logger.warning(f"[WeiboClient.get_creator_info_by_id] 使用默认 lfid_container_id: {container_info['lfid_container_id']}")

        user_res.update(container_info)
        return user_res

    async def get_notes_by_creator(
        self,
        creator: str,
        container_id: str,
        since_id: Optional[str] = "0",
        page: Optional[int] = None,
    ) -> Dict:
        """
        获取博主的笔记
        Args:
            creator: 博主ID
            container_id: 容器ID
            since_id: 上一页最后一条笔记的ID
        Returns:

        """

        uri = "/api/container/getIndex"
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator,
            "containerid": container_id,
        }
        if page is not None:
            params["page"] = page
        elif since_id is not None:
            params["since_id"] = since_id
        return await self.get(uri, params)

    async def get_all_notes_by_creator_id(
        self,
        creator_id: str,
        container_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> List[Dict]:
        """
        获取指定用户下的所有发过的帖子。
        默认限制为过去7天内的帖子；若配置 WEIBO_CREATOR_SINCE_DATE，则抓取该时间点之后的帖子。
        Args:
            creator_id:
            container_id:
            crawl_interval:
            callback:
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:

        """
        result: List[Dict] = []
        notes_has_more = True
        # 微博创作者页有两种翻页模式：
        # 1. 使用 since_id 游标
        # 2. 使用 page 页码（部分账号只返回 cardlistInfo.page）
        pagination_mode = "since_id"
        since_id: str = "0"
        current_page = 1
        crawler_total_count = 0
        is_first_request = True  # 标记是否为第一次请求
        seen_since_ids = {since_id}
        seen_pages = {current_page}
        seen_note_ids = set()
        consecutive_no_new_pages = 0
        max_consecutive_no_new_pages = 3

        since_date_value = getattr(config, "WEIBO_CREATOR_SINCE_DATE", "").strip()
        if since_date_value:
            try:
                if len(since_date_value) == 10:
                    since_dt = datetime.fromisoformat(f"{since_date_value}T00:00:00+08:00")
                else:
                    normalized_value = since_date_value.replace("Z", "+00:00")
                    since_dt = datetime.fromisoformat(normalized_value)
                    if since_dt.tzinfo is None:
                        since_dt = since_dt.replace(tzinfo=timezone(timedelta(hours=8)))
                since_ts = int(since_dt.timestamp())
                since_desc = f"{since_dt.isoformat()}"
            except ValueError:
                utils.logger.warning(
                    f"[WeiboClient.get_all_notes_by_creator_id] 无法解析 WEIBO_CREATOR_SINCE_DATE={since_date_value}，"
                    "回退为过去7天。"
                )
                seven_days_ago = datetime.now() - timedelta(days=7)
                since_ts = int(seven_days_ago.timestamp())
                since_desc = "过去7天"
        else:
            seven_days_ago = datetime.now() - timedelta(days=7)
            since_ts = int(seven_days_ago.timestamp())
            since_desc = "过去7天"

        while notes_has_more:
            # 第一次请求前增加延迟，避免在获取 creator 信息后立即请求笔记列表
            if is_first_request:
                await asyncio.sleep(crawl_interval)
                is_first_request = False
                utils.logger.info(f"[WeiboClient.get_all_notes_by_creator_id] 开始获取用户 {creator_id} 的笔记列表")
            
            # 重试机制
            notes_res = None
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    if pagination_mode == "page":
                        notes_res = await self.get_notes_by_creator(
                            creator_id,
                            container_id,
                            since_id=None,
                            page=current_page,
                        )
                    else:
                        notes_res = await self.get_notes_by_creator(
                            creator_id,
                            container_id,
                            since_id=since_id,
                            page=None,
                        )
                    break  # 成功获取数据，跳出重试循环
                except DataFetchError as e:
                    error_msg = str(e)
                    # 如果是 432 错误（反爬虫），等待后重试
                    if "432" in error_msg or "432" in str(e):
                        retry_count += 1
                        if retry_count <= max_retries:
                            wait_time = retry_delay * retry_count  # 指数退避
                            utils.logger.warning(
                                f"[WeiboClient.get_all_notes_by_creator_id] "
                                f"遇到反爬虫限制 (432)，等待 {wait_time} 秒后重试 ({retry_count}/{max_retries})"
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            utils.logger.error(
                                f"[WeiboClient.get_all_notes_by_creator_id] "
                                f"达到最大重试次数 ({max_retries})，停止获取数据"
                            )
                            notes_has_more = False
                            break
                    elif "captcha_required" in error_msg:
                        # 已经抓到部分数据时，后续页触发验证码就保留已有结果，不整轮作废
                        if result:
                            utils.logger.warning(
                                f"[WeiboClient.get_all_notes_by_creator_id] "
                                f"后续分页触发验证码，保留已抓取的 {len(result)} 条微博并结束。"
                                f" creator_id={creator_id}"
                            )
                            notes_has_more = False
                            break
                        raise
                    else:
                        # 其他错误直接抛出
                        raise
                except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
                    # 瞬时网络错误：服务器断开、连接超时等，等待后重试
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = retry_delay * retry_count
                        utils.logger.warning(
                            f"[WeiboClient.get_all_notes_by_creator_id] "
                            f"网络/连接错误 ({e!s})，等待 {wait_time} 秒后重试 ({retry_count}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        utils.logger.error(
                            f"[WeiboClient.get_all_notes_by_creator_id] "
                            f"达到最大重试次数 ({max_retries})，停止获取数据: {e}"
                        )
                        if result:
                            utils.logger.warning(
                                f"[WeiboClient.get_all_notes_by_creator_id] "
                                f"网络异常发生在已抓到部分数据之后，保留已抓取的 {len(result)} 条微博并结束。"
                                f" creator_id={creator_id}"
                            )
                            notes_has_more = False
                            break
                        notes_has_more = False
                        break
                except Exception as e:
                    utils.logger.error(
                        f"[WeiboClient.get_all_notes_by_creator_id] "
                        f"获取数据时发生未知错误: {e}"
                    )
                    raise

            if not notes_res:
                if result:
                    utils.logger.warning(
                        f"[WeiboClient.get_all_notes_by_creator_id] "
                        f"分页提前结束，但已有 {len(result)} 条微博，直接返回已抓取结果。creator_id={creator_id}"
                    )
                    break
                if retry_count > max_retries:
                    utils.logger.error(
                        f"[WeiboClient.get_all_notes_by_creator_id] "
                        f"由于反爬虫限制，无法继续获取用户 {creator_id} 的数据"
                    )
                else:
                    utils.logger.error(
                        f"[WeiboClient.get_all_notes_by_creator_id] "
                        f"无法获取用户 {creator_id} 的数据，可能已被限制访问"
                    )
                break

            if "cards" not in notes_res:
                utils.logger.info(f"[WeiboClient.get_all_notes_by_creator] No 'cards' key found in response: {notes_res}")
                break

            cardlist_info = notes_res.get("cardlistInfo", {})
            prev_since_id = since_id
            new_since_id = str(cardlist_info.get("since_id", "")).strip()
            next_page_raw = cardlist_info.get("page")
            next_page: Optional[int] = None
            if isinstance(next_page_raw, int):
                next_page = next_page_raw
            elif isinstance(next_page_raw, str) and next_page_raw.isdigit():
                next_page = int(next_page_raw)

            # 当接口没有 since_id，但返回 page 时，自动切换为 page 翻页。
            if pagination_mode != "page" and new_since_id in {"", "0", "None", "null"} and next_page and next_page > current_page:
                pagination_mode = "page"
                current_page = next_page
                seen_pages.add(current_page)
                utils.logger.info(
                    f"[WeiboClient.get_all_notes_by_creator_id] 切换为 page 分页模式，"
                    f"creator_id={creator_id}, next_page={current_page}"
                )
            elif pagination_mode == "page":
                if not next_page or next_page <= current_page:
                    utils.logger.info(
                        f"[WeiboClient.get_all_notes_by_creator_id] page 未推进（current={current_page}, next={next_page}），"
                        f"视为已到末页。creator_id={creator_id}"
                    )
                    notes_has_more = False
                elif next_page in seen_pages:
                    utils.logger.info(
                        f"[WeiboClient.get_all_notes_by_creator_id] page 出现循环（{next_page}），"
                        f"结束分页。creator_id={creator_id}"
                    )
                    notes_has_more = False
                else:
                    current_page = next_page
                    seen_pages.add(current_page)
            else:
                # since_id 模式：游标未推进或循环时结束分页，避免重复抓取
                if new_since_id == prev_since_id:
                    utils.logger.info(
                        f"[WeiboClient.get_all_notes_by_creator_id] since_id 未推进（仍为 {new_since_id}），"
                        f"视为已到末页，结束分页。creator_id={creator_id}"
                    )
                    notes_has_more = False
                elif new_since_id in seen_since_ids:
                    utils.logger.info(
                        f"[WeiboClient.get_all_notes_by_creator_id] since_id 出现循环（{new_since_id}），"
                        f"结束分页。creator_id={creator_id}"
                    )
                    notes_has_more = False
                seen_since_ids.add(new_since_id)

                if new_since_id in {"0", "", "None", "null"}:
                    notes_has_more = False
                since_id = new_since_id

            notes = notes_res["cards"]
            cardlist_info = notes_res.get("cardlistInfo", {})
            utils.logger.info(
                f"[WeiboClient.get_all_notes_by_creator] got user_id:{creator_id} "
                f"raw_cards={len(notes)}, cardlistInfo={cardlist_info}"
            )
            # 创作者页除了 card_type == 9，还会混入其他带有效 mblog 的微博卡片。
            # 只按 card_type 过滤会漏掉大量真实微博，因此改为按 mblog.id 判定。
            filtered_cards = self._filter_creator_mblog_cards(notes)
            utils.logger.info(
                f"[WeiboClient.get_all_notes_by_creator] user_id:{creator_id} "
                f"filtered_cards={len(filtered_cards)}"
            )
            notes = filtered_cards

            # 只保留过去七天的帖子，按发布时间过滤
            filtered_notes = []
            for note in notes:
                mblog = note.get("mblog", {})
                created_at = mblog.get("created_at", "")
                if not created_at:
                    continue
                # 微博返回的 created_at 可能为 "Wed May 29 23:59:22 +0800 2024"，需要转换为时间戳
                try:
                    # 解析微博标准时间字符串
                    created_at_ts = int(datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y').timestamp())
                    if created_at_ts >= since_ts:
                        filtered_notes.append(note)
                except Exception as e:
                    utils.logger.warning(f"[WeiboClient.get_all_notes_by_creator_id] 解析微博 created_at 字段失败: {created_at} - {e}")

            # 去重：同一用户分页中重复返回的微博不再重复处理，避免重复抓取/写入
            new_notes = []
            for note in filtered_notes:
                note_id = str(note.get("mblog", {}).get("id", "")).strip()
                if not note_id:
                    continue
                if note_id in seen_note_ids:
                    continue
                seen_note_ids.add(note_id)
                new_notes.append(note)

            utils.logger.info(
                f"[WeiboClient.get_all_notes_by_creator_id] user_id:{creator_id} "
                f"page={current_page}, since_id={since_id}, raw_cards={len(notes)}, "
                f"filtered_notes={len(filtered_notes)}, new_notes={len(new_notes)}"
            )

            if not new_notes:
                consecutive_no_new_pages += 1
                if consecutive_no_new_pages >= max_consecutive_no_new_pages:
                    utils.logger.info(
                        f"[WeiboClient.get_all_notes_by_creator_id] 连续 {max_consecutive_no_new_pages} 页无新增微博，"
                        f"结束分页。creator_id={creator_id}"
                    )
                    notes_has_more = False
            else:
                consecutive_no_new_pages = 0

            if callback and new_notes:
                callback_page_label = (
                    f"page={current_page}"
                    if pagination_mode == "page"
                    else f"since_id={prev_since_id}"
                )
                utils.logger.info(
                    f"[WeiboClient.get_all_notes_by_creator_id] "
                    f"准备写入分页微博，creator_id={creator_id}, {callback_page_label}, notes={len(new_notes)}"
                )
                try:
                    callback_result = await callback(new_notes)
                    utils.logger.info(
                        f"[WeiboClient.get_all_notes_by_creator_id] "
                        f"分页微博写入完成，creator_id={creator_id}, {callback_page_label}, "
                        f"notes={len(new_notes)}, callback_result={callback_result}"
                    )
                except Exception as exc:
                    utils.logger.error(
                        f"[WeiboClient.get_all_notes_by_creator_id] "
                        f"分页微博写入失败，creator_id={creator_id}, {callback_page_label}, "
                        f"notes={len(new_notes)}, err={exc}"
                    )
                    if result:
                        utils.logger.warning(
                            f"[WeiboClient.get_all_notes_by_creator_id] "
                            f"写入失败发生在已有部分结果之后，保留此前已抓取的 {len(result)} 条微博并结束。"
                            f" creator_id={creator_id}"
                        )
                        notes_has_more = False
                        break
                    raise
            # 添加随机延迟，使请求更自然，降低触发反爬虫的概率
            random_delay = random.uniform(0, 1)  # 0-1秒随机延迟
            await asyncio.sleep(crawl_interval + random_delay)
            result.extend(new_notes)
            crawler_total_count += len(new_notes)
            total_raw = notes_res.get("cardlistInfo", {}).get("total", 0)
            if progress_callback:
                try:
                    progress_callback(
                        {
                            "creator_id": creator_id,
                            "pagination_mode": pagination_mode,
                            "page": current_page,
                            "notes_total": crawler_total_count,
                            "page_notes": len(new_notes),
                            "raw_total": total_raw,
                            "since_id": since_id,
                        }
                    )
                except Exception as exc:
                    utils.logger.warning(
                        f"[WeiboClient.get_all_notes_by_creator_id] progress callback failed: {exc}"
                    )

            # 检查抓到的最早一条微博是否已早于截止时间，提前终止分页
            has_exceed_since_time = False
            for note in notes:
                mblog = note.get("mblog", {})
                created_at = mblog.get("created_at", "")
                try:
                    created_at_ts = int(datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y').timestamp())
                    if created_at_ts < since_ts:
                        has_exceed_since_time = True
                        break
                except Exception:
                    continue
            if has_exceed_since_time:
                utils.logger.info(
                    f"[WeiboClient.get_all_notes_by_creator_id] 已抓取到截止时间 {since_desc} 之前的微博，终止分页。creator_id={creator_id}"
                )
                break

            try:
                total = int(total_raw)
            except (TypeError, ValueError):
                total = 0
            # 不要覆盖前面触发的终止条件（如游标回环/无新增数据）
            notes_has_more = notes_has_more and (total > crawler_total_count)
        return result

    @staticmethod
    def _filter_creator_mblog_cards(cards: List[Dict]) -> List[Dict]:
        filtered_cards: List[Dict] = []
        for card in cards:
            mblog = card.get("mblog")
            if not isinstance(mblog, dict):
                continue
            note_id = str(mblog.get("id", "")).strip()
            if not note_id:
                continue
            filtered_cards.append(card)
        return filtered_cards
