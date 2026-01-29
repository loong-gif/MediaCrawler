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
# @Author  : persist1@126.com
# @Time    : 2025/9/5 19:34
# @Desc    : B站存储实现类
import asyncio
import csv
import json
import os
import pathlib
from typing import Dict

import aiofiles
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import config
from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.models import BilibiliVideoComment, BilibiliVideo, BilibiliUpInfo, BilibiliUpDynamic, BilibiliContactInfo
from tools.async_file_writer import AsyncFileWriter
from tools import utils, words
from var import crawler_type_var


class BiliCsvStoreImplement(AbstractStore):
    def __init__(self):
        self.file_writer = AsyncFileWriter(
            crawler_type=crawler_type_var.get(),
            platform="bilibili"
        )

    async def store_content(self, content_item: Dict):
        """
        content CSV storage implementation
        Args:
            content_item:

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=content_item,
            item_type="videos"
        )

    async def store_comment(self, comment_item: Dict):
        """
        comment CSV storage implementation
        Args:
            comment_item:

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=comment_item,
            item_type="comments"
        )

    async def store_creator(self, creator: Dict):
        """
        creator CSV storage implementation
        Args:
            creator:

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=creator,
            item_type="creators"
        )

    async def store_contact(self, contact_item: Dict):
        """
        creator contact CSV storage implementation
        Args:
            contact_item: creator's contact item dict

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=contact_item,
            item_type="contacts"
        )

    async def store_dynamic(self, dynamic_item: Dict):
        """
        creator dynamic CSV storage implementation
        Args:
            dynamic_item: creator's contact item dict

        Returns:

        """
        await self.file_writer.write_to_csv(
            item=dynamic_item,
            item_type="dynamics"
        )


class BiliDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        """
        Bilibili content DB storage implementation
        Args:
            content_item: content item dict
        """
        video_id = content_item.get("video_id")
        # Convert video_id to int for BigInteger field (PostgreSQL requires type matching)
        video_id_int = int(video_id) if video_id else None
        async with get_session() as session:
            result = await session.execute(select(BilibiliVideo).where(BilibiliVideo.video_id == video_id_int))
            video_detail = result.scalar_one_or_none()

            if not video_detail:
                content_item["add_ts"] = utils.get_current_timestamp()
                # Convert all BigInteger and Integer fields to int for PostgreSQL
                bigint_fields = ["video_id", "user_id", "add_ts", "last_modify_ts", "create_time"]
                integer_fields = ["liked_count"]  # Add other Integer fields if needed
                string_fields = ["disliked_count", "video_play_count", "video_favorite_count", "video_share_count", "video_coin_count", "video_danmaku", "video_comment"]
                
                for field in bigint_fields + integer_fields:
                    if field in content_item and content_item[field] is not None:
                        try:
                            content_item[field] = int(content_item[field])
                        except (ValueError, TypeError):
                            # If conversion fails, set to None
                            content_item[field] = None
                
                # Ensure Text/String fields are strings
                for field in string_fields:
                    if field in content_item and content_item[field] is not None:
                        content_item[field] = str(content_item[field])
                
                # Ensure video_url exists (required field)
                if not content_item.get("video_url"):
                    content_item["video_url"] = f"https://www.bilibili.com/video/av{content_item.get('video_id', '')}"
                
                try:
                    new_content = BilibiliVideo(**content_item)
                    session.add(new_content)
                    utils.logger.debug(f"[store_content] 添加视频到session: video_id={video_id_int}")
                except Exception as e:
                    utils.logger.error(f"创建BilibiliVideo对象失败: {e}, content_item keys: {list(content_item.keys())}")
                    raise
            else:
                for key, value in content_item.items():
                    # Convert BigInteger and Integer fields to int when updating
                    if key in ["video_id", "user_id", "add_ts", "last_modify_ts", "create_time", "liked_count"] and value is not None:
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            value = None
                    # Ensure Text/String fields are strings
                    elif key in ["disliked_count", "video_play_count", "video_favorite_count", "video_share_count", "video_coin_count", "video_danmaku", "video_comment"] and value is not None:
                        value = str(value)
                    setattr(video_detail, key, value)
            # 移除 await session.commit() - 让上下文管理器自动提交

    async def store_comment(self, comment_item: Dict):
        """
        Bilibili comment DB storage implementation
        Args:
            comment_item: comment item dict
        """
        comment_id = comment_item.get("comment_id")
        # Convert comment_id to int for BigInteger field (PostgreSQL requires type matching)
        comment_id_int = int(comment_id) if comment_id else None
        async with get_session() as session:
            result = await session.execute(select(BilibiliVideoComment).where(BilibiliVideoComment.comment_id == comment_id_int))
            comment_detail = result.scalar_one_or_none()

            if not comment_detail:
                comment_item["add_ts"] = utils.get_current_timestamp()
                # Convert all BigInteger fields to int for PostgreSQL
                bigint_fields = ["comment_id", "video_id", "add_ts", "last_modify_ts", "create_time"]
                for field in bigint_fields:
                    if field in comment_item and comment_item[field] is not None:
                        try:
                            comment_item[field] = int(comment_item[field])
                        except (ValueError, TypeError):
                            comment_item[field] = None
                # Ensure Text/String fields are strings (even if they come as int)
                text_fields = ["like_count", "sub_comment_count", "parent_comment_id", "user_id"]
                for field in text_fields:
                    if field in comment_item and comment_item[field] is not None:
                        comment_item[field] = str(comment_item[field])
                try:
                    new_comment = BilibiliVideoComment(**comment_item)
                    session.add(new_comment)
                    utils.logger.debug(f"[store_comment] 添加评论到session: comment_id={comment_id_int}")
                except Exception as e:
                    utils.logger.error(f"创建BilibiliVideoComment对象失败: {e}, comment_item keys: {list(comment_item.keys())}")
                    raise
            else:
                for key, value in comment_item.items():
                    # Convert BigInteger fields to int when updating
                    if key in ("comment_id", "video_id", "add_ts", "last_modify_ts", "create_time") and value is not None:
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            value = None
                    # Ensure Text/String fields are strings
                    elif key in ("like_count", "sub_comment_count", "parent_comment_id", "user_id") and value is not None:
                        value = str(value)
                    setattr(comment_detail, key, value)
            # 移除 await session.commit() - 让上下文管理器自动提交

    async def store_creator(self, creator: Dict):
        """
        Bilibili creator DB storage implementation
        Args:
            creator: creator item dict
        """
        creator_id = creator.get("user_id")
        # Convert user_id to int for BigInteger field (PostgreSQL requires type matching)
        creator_id_int = int(creator_id) if creator_id else None
        async with get_session() as session:
            result = await session.execute(select(BilibiliUpInfo).where(BilibiliUpInfo.user_id == creator_id_int))
            creator_detail = result.scalar_one_or_none()

            if not creator_detail:
                creator["add_ts"] = utils.get_current_timestamp()
                # Convert all BigInteger and Integer fields to int for PostgreSQL
                bigint_fields = ["user_id", "add_ts", "last_modify_ts"]
                integer_fields = ["total_fans", "total_liked", "user_rank", "is_official"]
                for field in bigint_fields + integer_fields:
                    if field in creator and creator[field] is not None:
                        try:
                            creator[field] = int(creator[field])
                        except (ValueError, TypeError):
                            creator[field] = None
                try:
                    new_creator = BilibiliUpInfo(**creator)
                    session.add(new_creator)
                    utils.logger.debug(f"[store_creator] 添加UP信息到session: user_id={creator_id_int}")
                except Exception as e:
                    utils.logger.error(f"创建BilibiliUpInfo对象失败: {e}, creator keys: {list(creator.keys())}")
                    raise
            else:
                for key, value in creator.items():
                    # Convert BigInteger and Integer fields to int when updating
                    if key in ("user_id", "add_ts", "last_modify_ts", "total_fans", "total_liked", "user_rank", "is_official") and value is not None:
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            value = None
                    setattr(creator_detail, key, value)
            # 移除 await session.commit() - 让上下文管理器自动提交

    async def store_contact(self, contact_item: Dict):
        """
        Bilibili contact DB storage implementation
        Args:
            contact_item: contact item dict
        """
        up_id = contact_item.get("up_id")
        fan_id = contact_item.get("fan_id")
        # Convert to int for BigInteger fields (PostgreSQL requires type matching)
        up_id_int = int(up_id) if up_id else None
        fan_id_int = int(fan_id) if fan_id else None
        async with get_session() as session:
            result = await session.execute(
                select(BilibiliContactInfo).where(BilibiliContactInfo.up_id == up_id_int, BilibiliContactInfo.fan_id == fan_id_int)
            )
            contact_detail = result.scalar_one_or_none()

            if not contact_detail:
                contact_item["add_ts"] = utils.get_current_timestamp()
                # Convert all BigInteger fields to int for PostgreSQL
                bigint_fields = ["up_id", "fan_id", "add_ts", "last_modify_ts"]
                for field in bigint_fields:
                    if field in contact_item and contact_item[field]:
                        try:
                            contact_item[field] = int(contact_item[field])
                        except (ValueError, TypeError):
                            pass
                new_contact = BilibiliContactInfo(**contact_item)
                session.add(new_contact)
            else:
                for key, value in contact_item.items():
                    # Convert BigInteger fields to int when updating
                    if key in ("up_id", "fan_id", "add_ts", "last_modify_ts") and value:
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            pass
                    setattr(contact_detail, key, value)
            # 移除 await session.commit() - 让上下文管理器自动提交

    async def store_dynamic(self, dynamic_item):
        """
        Bilibili dynamic DB storage implementation
        Args:
            dynamic_item: dynamic item dict
        """
        dynamic_id = dynamic_item.get("dynamic_id")
        # Convert dynamic_id to int for BigInteger field (PostgreSQL requires type matching)
        dynamic_id_int = int(dynamic_id) if dynamic_id else None
        async with get_session() as session:
            result = await session.execute(select(BilibiliUpDynamic).where(BilibiliUpDynamic.dynamic_id == dynamic_id_int))
            dynamic_detail = result.scalar_one_or_none()

            if not dynamic_detail:
                dynamic_item["add_ts"] = utils.get_current_timestamp()
                # Convert all BigInteger and Integer fields to int for PostgreSQL
                bigint_fields = ["dynamic_id", "pub_ts", "add_ts", "last_modify_ts"]
                integer_fields = ["total_comments", "total_forwards", "total_liked"]
                for field in bigint_fields + integer_fields:
                    if field in dynamic_item and dynamic_item[field] is not None:
                        try:
                            dynamic_item[field] = int(dynamic_item[field])
                        except (ValueError, TypeError):
                            dynamic_item[field] = None
                new_dynamic = BilibiliUpDynamic(**dynamic_item)
                session.add(new_dynamic)
            else:
                for key, value in dynamic_item.items():
                    # Convert BigInteger and Integer fields to int when updating
                    if key in ("dynamic_id", "pub_ts", "add_ts", "last_modify_ts", "total_comments", "total_forwards", "total_liked") and value is not None:
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            value = None
                    setattr(dynamic_detail, key, value)
            # 移除 await session.commit() - 让上下文管理器自动提交


class BiliJsonStoreImplement(AbstractStore):
    def __init__(self):
        self.file_writer = AsyncFileWriter(
            crawler_type=crawler_type_var.get(),
            platform="bilibili"
        )

    async def store_content(self, content_item: Dict):
        """
        content JSON storage implementation
        Args:
            content_item:

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=content_item,
            item_type="contents"
        )

    async def store_comment(self, comment_item: Dict):
        """
        comment JSON storage implementation
        Args:
            comment_item:

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=comment_item,
            item_type="comments"
        )

    async def store_creator(self, creator: Dict):
        """
        creator JSON storage implementation
        Args:
            creator:

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=creator,
            item_type="creators"
        )

    async def store_contact(self, contact_item: Dict):
        """
        creator contact JSON storage implementation
        Args:
            contact_item: creator's contact item dict

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=contact_item,
            item_type="contacts"
        )

    async def store_dynamic(self, dynamic_item: Dict):
        """
        creator dynamic JSON storage implementation
        Args:
            dynamic_item: creator's contact item dict

        Returns:

        """
        await self.file_writer.write_single_item_to_json(
            item=dynamic_item,
            item_type="dynamics"
        )



class BiliSqliteStoreImplement(BiliDbStoreImplement):
    pass
