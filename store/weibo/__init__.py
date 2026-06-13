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
# @Time    : 2024/1/14 21:34
# @Desc    :

import json
import re
import asyncio
import pathlib
from typing import Dict, List, Union
from urllib.parse import urlparse

import httpx
import aiofiles

from var import source_keyword_var
from tools import utils
from config import base_config

from .weibo_store_media import *
from ._store_impl import *


WEIBO_MEDIA_DOWNLOAD_FILTER_ALL = "all"
WEIBO_MEDIA_DOWNLOAD_FILTER_SELFIE_TRUE = "is_selfie_true"
WEIBO_MEDIA_DOWNLOAD_FILTER_OPTIONS = {
    WEIBO_MEDIA_DOWNLOAD_FILTER_ALL,
    WEIBO_MEDIA_DOWNLOAD_FILTER_SELFIE_TRUE,
}


def get_weibo_media_download_filter() -> str:
    download_filter = str(
        getattr(base_config, "WEIBO_MEDIA_DOWNLOAD_FILTER", WEIBO_MEDIA_DOWNLOAD_FILTER_ALL)
    ).strip().lower()
    if download_filter not in WEIBO_MEDIA_DOWNLOAD_FILTER_OPTIONS:
        raise ValueError(
            "Invalid WEIBO_MEDIA_DOWNLOAD_FILTER. "
            f"Expected one of {sorted(WEIBO_MEDIA_DOWNLOAD_FILTER_OPTIONS)}, got: {download_filter!r}"
        )
    return download_filter


def sanitize_weibo_media_filename(filename: str, *, max_length: int = 200) -> str:
    sanitized = re.sub(r"\s+", "_", str(filename or "").strip())
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized).strip("._")
    if not sanitized:
        sanitized = "unknown"
    return sanitized[:max_length]


def build_weibo_crawl_image_filename(
    *,
    nickname: str,
    date_part: str,
    content_part: str,
    image_index: int,
    image_count: int,
) -> str:
    filename_parts = [
        sanitize_weibo_media_filename(nickname or "unknown"),
        sanitize_weibo_media_filename(date_part or "unknown"),
        sanitize_weibo_media_filename(content_part or "content"),
    ]
    if image_count > 1:
        filename_parts.append(str(image_index))
    return "_".join(filename_parts)


def build_weibo_selfie_image_filename(*, note_id: Union[int, str], image_index: Union[int, str]) -> str:
    return sanitize_weibo_media_filename(f"{note_id}_{image_index}")


async def download_weibo_image(image_url: str, save_path: str, filename: str) -> bool:
    """
    下载微博图片到本地
    Args:
        image_url: 图片URL
        save_path: 保存路径（目录）
        filename: 文件名（不包含扩展名，扩展名会从URL自动提取）
    Returns:
        bool: 是否下载成功
    """
    try:
        # 确保保存目录存在
        pathlib.Path(save_path).mkdir(parents=True, exist_ok=True)
        
        # 从URL提取文件扩展名
        parsed_url = urlparse(image_url)
        ext = pathlib.Path(parsed_url.path).suffix or ".jpg"
        if not ext.startswith("."):
            ext = "." + ext
        
        # 清理文件名中的非法字符
        # Windows文件名不能包含: < > : " / \ | ? *
        clean_filename = sanitize_weibo_media_filename(filename)
        
        full_filename = f"{clean_filename}{ext}"
        filepath = pathlib.Path(save_path) / full_filename
        
        # 如果文件已存在，跳过下载
        if filepath.exists():
            utils.logger.debug(f"[store.weibo.download_weibo_image] 图片已存在，跳过: {full_filename}")
            return True
        
        # 下载图片
        # 微博图片可能需要通过代理访问，使用简单的httpx请求
        proxy = None
        if base_config.ENABLE_IP_PROXY:
            # 如果需要代理，可以从代理池获取
            # 这里简化处理，直接使用None
            pass
        
        async with httpx.AsyncClient(proxy=proxy, timeout=30.0, follow_redirects=True) as client:
            # 设置请求头，模拟浏览器
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://weibo.com/",
            }
            response = await client.get(image_url, headers=headers)
            response.raise_for_status()
            
            # 保存图片
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(response.content)
            
            utils.logger.info(f"[store.weibo.download_weibo_image] 下载成功: {full_filename}")
            return True
            
    except Exception as e:
        utils.logger.error(f"[store.weibo.download_weibo_image] 下载失败 {image_url}: {e}")
        return False


class WeibostoreFactory:
    STORES = {
        "csv": WeiboCsvStoreImplement,
        "db": WeiboDbStoreImplement,
        "json": WeiboJsonStoreImplement,
        "sqlite": WeiboSqliteStoreImplement,
        "supabase": WeiboSupabaseStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        import config
        store_class = WeibostoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError("[WeibotoreFactory.create_store] Invalid save option only supported csv or db or json or sqlite or supabase ...")
        return store_class()


async def batch_update_weibo_notes(note_list: List[Dict]):
    """
    Batch update weibo notes
    Args:
        note_list:

    Returns:

    """
    if not note_list:
        return
    utils.logger.info(
        f"[store.weibo.batch_update_weibo_notes] received batch with {len(note_list)} notes"
    )
    stored_count = 0
    failed_count = 0
    first_error = None
    for note_item in note_list:
        note_id = str((note_item.get("mblog") or {}).get("id", "")).strip()
        try:
            await update_weibo_note(note_item)
            stored_count += 1
        except Exception as exc:
            failed_count += 1
            if first_error is None:
                first_error = exc
            utils.logger.error(
                f"[store.weibo.batch_update_weibo_notes] failed to store note_id={note_id or 'unknown'}, err={exc}"
            )
    summary = {
        "received": len(note_list),
        "stored": stored_count,
        "failed": failed_count,
    }
    utils.logger.info(
        f"[store.weibo.batch_update_weibo_notes] completed batch summary={summary}"
    )
    if stored_count == 0 and first_error is not None:
        raise first_error
    return summary


async def update_weibo_note(note_item: Dict):
    """
    Update weibo note
    Args:
        note_item:

    Returns:

    """
    if not note_item:
        return

    mblog = note_item.get("mblog") or {}
    if not isinstance(mblog, dict):
        raise ValueError("Invalid note item: missing mblog payload")
    user_info = mblog.get("user") or {}
    if not isinstance(user_info, dict):
        user_info = {}
    note_id = mblog.get("id")
    # 确保 note_id 是整数类型（数据库字段是 BigInteger）
    note_id_int = int(note_id) if note_id else None
    if note_id_int is None:
        raise ValueError("Invalid note item: missing note_id")
    content_text = mblog.get("text") or ""
    clean_text = re.sub(r"<.*?>", "", str(content_text))
    
    # 提取图片链接列表
    image_list = []
    pics = mblog.get("pics")
    
    # 调试：记录pics的数据结构
    if pics:
        utils.logger.debug(f"[store.weibo.update_weibo_note] note_id: {note_id}, pics类型: {type(pics)}, pics内容: {str(pics)[:200]}")
    
    if pics and isinstance(pics, list):
        for idx, pic in enumerate(pics):
            # 尝试多种方式获取图片URL
            pic_url = None
            if isinstance(pic, dict):
                # 方式1: 直接获取url字段
                pic_url = pic.get("url")
                
                # 方式2: 如果没有url，尝试从large字段获取
                if not pic_url:
                    large_pic = pic.get("large", {})
                    if isinstance(large_pic, dict):
                        pic_url = large_pic.get("url")
                
                # 方式3: 尝试从original字段获取
                if not pic_url:
                    original_pic = pic.get("original", {})
                    if isinstance(original_pic, dict):
                        pic_url = original_pic.get("url")
                
                # 方式4: 尝试从pid构建URL（如果只有pid）
                if not pic_url:
                    pid = pic.get("pid")
                    if pid:
                        # 微博图片URL格式: https://wx1.sinaimg.cn/large/{pid}.jpg
                        pic_url = f"https://wx1.sinaimg.cn/large/{pid}.jpg"
                
                # 方式5: 尝试从其他可能的字段获取
                if not pic_url:
                    # 尝试获取其他可能的URL字段
                    for key in ["pic_url", "picUrl", "image_url", "imageUrl", "src"]:
                        if key in pic:
                            pic_url = pic.get(key)
                            if pic_url:
                                break
                
                # 调试：如果仍然没有找到URL，记录pic的完整内容
                if not pic_url:
                    utils.logger.debug(f"[store.weibo.update_weibo_note] note_id: {note_id}, 图片{idx}未找到URL, pic内容: {str(pic)[:200]}")
            
            if pic_url:
                # 转换为高清大图链接（如果需要）
                if "sinaimg.cn" in pic_url:
                    # 确保是高清大图链接
                    if "/large/" not in pic_url:
                        if "/bmiddle/" in pic_url:
                            pic_url = pic_url.replace("/bmiddle/", "/large/")
                        elif "/thumbnail/" in pic_url:
                            pic_url = pic_url.replace("/thumbnail/", "/large/")
                        elif "/orj360/" in pic_url:
                            pic_url = pic_url.replace("/orj360/", "/large/")
                        elif "/orj480/" in pic_url:
                            pic_url = pic_url.replace("/orj480/", "/large/")
                        elif "/small/" in pic_url:
                            pic_url = pic_url.replace("/small/", "/large/")
                        # 如果URL中没有尺寸标识，尝试添加/large/
                        elif "/large/" not in pic_url and "/bmiddle/" not in pic_url:
                            # 检查是否是直接的图片ID格式
                            if pic_url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                                # 如果URL格式是 https://wxX.sinaimg.cn/xxx.jpg，替换为 /large/
                                pic_url = re.sub(r'/([^/]+\.(jpg|jpeg|png|gif|webp))$', r'/large/\1', pic_url)
                
                image_list.append(pic_url)
                utils.logger.debug(f"[store.weibo.update_weibo_note] note_id: {note_id}, 提取到图片{idx}: {pic_url}")
    
    # 将图片链接列表转换为JSON字符串保存
    image_list_str = json.dumps(image_list, ensure_ascii=False) if image_list else ""
    
    # 记录图片链接提取结果
    if image_list:
        utils.logger.info(f"[store.weibo.update_weibo_note] note_id: {note_id}, 提取到 {len(image_list)} 张图片: {image_list_str[:200]}")
    elif pics:
        utils.logger.warning(f"[store.weibo.update_weibo_note] note_id: {note_id}, 检测到pics但未提取到有效图片链接, pics: {str(pics)[:300]}")
    
    save_content_item = {
        # 微博信息
        "note_id": note_id_int,
        "content": clean_text,
        "created_at": mblog.get("created_at", ""),
        "create_time": utils.rfc2822_to_timestamp(mblog.get("created_at")),
        "create_date_time": str(utils.rfc2822_to_china_datetime(mblog.get("created_at"))),
        "liked_count": str(mblog.get("attitudes_count", 0)),
        "comments_count": str(mblog.get("comments_count", 0)),
        "shared_count": str(mblog.get("reposts_count", 0)),
        "last_modify_ts": utils.get_current_timestamp(),
        "note_url": f"https://m.weibo.cn/detail/{note_id}",
        "ip_location": mblog.get("region_name", "").replace("发布于 ", ""),
        "image_list": image_list_str,  # 保存图片链接列表（JSON格式字符串）

        # 用户信息
        "user_id": str(user_info.get("id")),
        "nickname": user_info.get("screen_name", ""),
        "gender": user_info.get("gender", ""),
        "profile_url": user_info.get("profile_url", ""),
        "avatar": user_info.get("profile_image_url", ""),
        "source_keyword": source_keyword_var.get(),
    }
    utils.logger.info(
        f"[store.weibo.update_weibo_note] prepared note_id={note_id_int}, user_id={save_content_item['user_id']}, image_count={len(image_list)}"
    )
    
    # 调试：确认 image_list 字段的值
    if image_list_str:
        utils.logger.info(f"[store.weibo.update_weibo_note] note_id: {note_id}, 准备保存 image_list: {image_list_str[:200]}")
    else:
        utils.logger.debug(f"[store.weibo.update_weibo_note] note_id: {note_id}, image_list 为空")
    
    # 下载图片到本地
    if image_list and base_config.ENABLE_GET_MEIDAS:
        download_filter = get_weibo_media_download_filter()
        if download_filter == WEIBO_MEDIA_DOWNLOAD_FILTER_SELFIE_TRUE:
            utils.logger.info(
                "[store.weibo.update_weibo_note] "
                f"note_id: {note_id}, skip crawl-time download because "
                f"WEIBO_MEDIA_DOWNLOAD_FILTER={download_filter}"
            )
        else:
            image_store_path = "data/weibo/images"
            utils.logger.info(f"[store.weibo.update_weibo_note] note_id: {note_id}, 开始下载 {len(image_list)} 张图片...")

            # 准备文件名组件
            nickname = user_info.get("screen_name", "unknown")
            # 从 create_date_time 提取日期部分 (格式: yyyy-MM-dd HH:mm:ss)
            create_date_time_str = save_content_item.get("create_date_time", "")
            date_part = ""
            if create_date_time_str:
                try:
                    date_part = create_date_time_str.split()[0]
                except Exception:
                    date_part = create_date_time_str[:10] if len(create_date_time_str) >= 10 else ""

            content_part = clean_text[:30] if clean_text else ""

            # 串行下载图片（避免请求过快，每张图片之间等待）
            success_count = 0
            for idx, pic_url in enumerate(image_list, start=1):
                filename = build_weibo_crawl_image_filename(
                    nickname=nickname,
                    date_part=date_part,
                    content_part=content_part,
                    image_index=idx,
                    image_count=len(image_list),
                )

                result = await download_weibo_image(pic_url, image_store_path, filename)
                if result:
                    success_count += 1

                if idx < len(image_list):
                    await asyncio.sleep(0.5)

            utils.logger.info(
                f"[store.weibo.update_weibo_note] note_id: {note_id}, 图片下载完成: {success_count}/{len(image_list)} 成功"
            )
    
    utils.logger.info(f"[store.weibo.update_weibo_note] weibo note id:{note_id}, title:{save_content_item.get('content')[:24]} ...")
    await WeibostoreFactory.create_store().store_content(content_item=save_content_item)
    utils.logger.info(
        f"[store.weibo.update_weibo_note] stored note_id={note_id_int}, user_id={save_content_item['user_id']}"
    )


async def batch_update_weibo_note_comments(note_id: str, comments: List[Dict]):
    """
    Batch update weibo note comments
    Args:
        note_id:
        comments:

    Returns:

    """
    if not comments:
        return
    for comment_item in comments:
        await update_weibo_note_comment(note_id, comment_item)


async def update_weibo_note_comment(note_id: str, comment_item: Dict):
    """
    Update weibo note comment
    Args:
        note_id: weibo note id
        comment_item: weibo comment item

    Returns:

    """
    if not comment_item or not note_id:
        return
    comment_id_raw = comment_item.get("id")
    # 确保 comment_id 是整数类型（数据库字段是 BigInteger）
    comment_id = int(comment_id_raw) if comment_id_raw else None
    # 确保 note_id 是整数类型（数据库字段是 BigInteger）
    note_id_int = int(note_id) if note_id else None
    user_info: Dict = comment_item.get("user")
    content_text = comment_item.get("text")
    clean_text = re.sub(r"<.*?>", "", content_text)
    save_comment_item = {
        "comment_id": comment_id,
        "create_time": utils.rfc2822_to_timestamp(comment_item.get("created_at")),
        "create_date_time": str(utils.rfc2822_to_china_datetime(comment_item.get("created_at"))),
        "note_id": note_id_int,
        "content": clean_text,
        "sub_comment_count": str(comment_item.get("total_number", 0)),
        "comment_like_count": str(comment_item.get("like_count", 0)),
        "last_modify_ts": utils.get_current_timestamp(),
        "ip_location": comment_item.get("source", "").replace("来自", ""),
        "parent_comment_id": comment_item.get("rootid", ""),

        # 用户信息
        "user_id": str(user_info.get("id")),
        "nickname": user_info.get("screen_name", ""),
        "gender": user_info.get("gender", ""),
        "profile_url": user_info.get("profile_url", ""),
        "avatar": user_info.get("profile_image_url", ""),
    }
    utils.logger.info(f"[store.weibo.update_weibo_note_comment] Weibo note comment: {comment_id}, content: {save_comment_item.get('content', '')[:24]} ...")
    await WeibostoreFactory.create_store().store_comment(comment_item=save_comment_item)


async def update_weibo_note_image(picid: str, pic_content, extension_file_name):
    """
    Save weibo note image to local
    Args:
        picid:
        pic_content:
        extension_file_name:

    Returns:

    """
    await WeiboStoreImage().store_image({"pic_id": picid, "pic_content": pic_content, "extension_file_name": extension_file_name})


async def save_creator(user_id: str, user_info: Dict):
    """
    Save creator information to local
    Args:
        user_id:
        user_info:

    Returns:

    """
    local_db_item = {
        'user_id': user_id,
        'nickname': user_info.get('screen_name'),
        'gender': '女' if user_info.get('gender') == "f" else '男',
        'avatar': user_info.get('avatar_hd'),
        'desc': user_info.get('description'),
        'ip_location': user_info.get("source", "").replace("来自", ""),
        'follows': str(user_info.get('follow_count', '') or ''),
        'fans': str(user_info.get('followers_count', '') or ''),
        'tag_list': '',
        "last_modify_ts": utils.get_current_timestamp(),
    }
    utils.logger.info(f"[store.weibo.save_creator] creator:{local_db_item}")
    await WeibostoreFactory.create_store().store_creator(local_db_item)
