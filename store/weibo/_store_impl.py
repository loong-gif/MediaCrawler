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
# @Desc    : 微博存储实现类
import asyncio
import csv
import json
import os
import pathlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import aiofiles
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from base.base_crawler import AbstractStore
from database.models import WeiboCreator, WeiboNote, WeiboNoteComment
from database.weibo_supabase_models import SupabaseWeiboCreator, SupabaseWeiboImage, SupabaseWeiboNote
from database.weibo_supabase_session import get_supabase_session
from tools import utils, words
from tools.async_file_writer import AsyncFileWriter
from database.db_session import get_session
from tools.weibo_supabase_import_utils import build_weibo_image_rows, plan_weibo_image_upserts
from var import crawler_type_var


async def _sync_weibo_creator_note_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(WeiboNote).where(WeiboNote.user_id == str(user_id))
    )
    note_count = int(result.scalar_one() or 0)
    creator_result = await session.execute(select(WeiboCreator).where(WeiboCreator.user_id == str(user_id)))
    db_creator = creator_result.scalar_one_or_none()
    if db_creator:
        db_creator.note_count = note_count
        db_creator.last_modify_ts = utils.get_current_timestamp()
    return note_count


class SupabaseWeiboRestStore:
    _project_ref: str = ""
    _service_role_key: str = ""

    @classmethod
    def _load_project_ref(cls) -> str:
        if cls._project_ref:
            return cls._project_ref
        project_ref_path = Path(__file__).resolve().parents[2] / "supabase" / ".temp" / "project-ref"
        if not project_ref_path.exists():
            raise RuntimeError(f"Supabase project ref file not found: {project_ref_path}")
        cls._project_ref = project_ref_path.read_text(encoding="utf-8").strip()
        return cls._project_ref

    @classmethod
    def _load_service_role_key(cls) -> str:
        if cls._service_role_key:
            return cls._service_role_key
        project_ref = cls._load_project_ref()
        result = subprocess.run(
            ["supabase", "projects", "api-keys", "--project-ref", project_ref, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to fetch Supabase API keys")
        payload = json.loads(result.stdout)
        for item in payload:
            if item.get("name") == "service_role" and item.get("api_key"):
                cls._service_role_key = item["api_key"]
                return cls._service_role_key
        raise RuntimeError("No usable service_role API key found for Supabase project")

    @classmethod
    async def _request(
        cls,
        *,
        method: str,
        table_name: str,
        params: Optional[Dict] = None,
        json_body=None,
        prefer: Optional[str] = None,
    ):
        project_ref = cls._load_project_ref()
        service_role_key = cls._load_service_role_key()
        url = f"https://{project_ref}.supabase.co/rest/v1/{table_name}"
        headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer

        last_exc: Optional[Exception] = None
        for attempt in range(1, 6):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        headers=headers,
                        json=json_body,
                    )
                response.raise_for_status()
                if not response.content:
                    return None
                if "application/json" in response.headers.get("content-type", ""):
                    return response.json()
                return response.text
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt == 5:
                    break
                wait_seconds = attempt * 2
                utils.logger.warning(
                    f"[SupabaseWeiboRestStore._request] transient error on {table_name}, retry {attempt}/5 after {wait_seconds}s: {exc}"
                )
                await asyncio.sleep(wait_seconds)
        if last_exc is not None:
            raise last_exc

    @classmethod
    async def upsert_many(cls, *, table_name: str, conflict_field: str, rows: list[Dict]):
        if not rows:
            return
        await cls._request(
            method="POST",
            table_name=table_name,
            params={"on_conflict": conflict_field},
            json_body=rows,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    @classmethod
    async def upsert(cls, *, table_name: str, conflict_field: str, row: Dict):
        await cls.upsert_many(table_name=table_name, conflict_field=conflict_field, rows=[row])

    @classmethod
    async def fetch_rows(
        cls,
        *,
        table_name: str,
        select_fields: str,
        filters: Optional[Dict[str, str]] = None,
        order_by: Optional[str] = None,
    ) -> list[Dict]:
        params = {"select": select_fields}
        if filters:
            params.update(filters)
        if order_by:
            params["order"] = order_by
        payload = await cls._request(method="GET", table_name=table_name, params=params)
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected response when reading {table_name}: {payload}")
        return payload

    @classmethod
    async def delete_rows(cls, *, table_name: str, filters: Dict[str, str]):
        if not filters:
            return
        await cls._request(
            method="DELETE",
            table_name=table_name,
            params=filters,
            prefer="return=minimal",
        )


def calculate_number_of_files(file_store_path: str) -> int:
    """计算数据保存文件的前部分排序数字，支持每次运行代码不写到同一个文件中
    Args:
        file_store_path;
    Returns:
        file nums
    """
    if not os.path.exists(file_store_path):
        return 1
    try:
        return max([int(file_name.split("_")[0]) for file_name in os.listdir(file_store_path)]) + 1
    except ValueError:
        return 1


class WeiboCsvStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="weibo", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """
        Weibo content CSV storage implementation
        Args:
            content_item: note item dict

        Returns:

        """
        await self.writer.write_to_csv(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        Weibo comment CSV storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """
        await self.writer.write_to_csv(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        """
        Weibo creator CSV storage implementation
        Args:
            creator:

        Returns:

        """
        await self.writer.write_to_csv(item_type="creators", item=creator)


class WeiboDbStoreImplement(AbstractStore):

    async def store_content(self, content_item: Dict):
        """
        Weibo content DB storage implementation
        Args:
            content_item: content item dict

        Returns:

        """
        note_id = content_item.get("note_id")
        # 确保 note_id 是整数类型（数据库字段是 BigInteger）
        if note_id is not None:
            note_id = int(note_id) if not isinstance(note_id, int) else note_id
        async with get_session() as session:
            stmt = select(WeiboNote).where(WeiboNote.note_id == note_id)
            res = await session.execute(stmt)
            db_note = res.scalar_one_or_none()
            if db_note:
                # 更新已存在的记录：只更新非主键字段
                db_note.last_modify_ts = utils.get_current_timestamp()
                # 定义主键字段和不应更新的字段
                primary_key_fields = {'id'}  # 主键字段
                excluded_fields = {'add_ts'}  # 不应更新的字段（只在创建时设置）
                
                for key, value in content_item.items():
                    # 跳过主键字段和不应更新的字段
                    if key in primary_key_fields or key in excluded_fields:
                        continue
                    # 只更新存在的字段
                    if hasattr(db_note, key):
                        setattr(db_note, key, value)
            else:
                # 创建新记录
                content_item["add_ts"] = utils.get_current_timestamp()
                content_item["last_modify_ts"] = utils.get_current_timestamp()
                db_note = WeiboNote(**content_item)
                session.add(db_note)
            await _sync_weibo_creator_note_count(session, int(content_item["user_id"]))
            await session.commit()

    async def store_comment(self, comment_item: Dict):
        """
        Weibo content DB storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """
        comment_id = comment_item.get("comment_id")
        # 确保 comment_id 是整数类型（数据库字段是 BigInteger）
        if comment_id is not None:
            comment_id = int(comment_id) if not isinstance(comment_id, int) else comment_id
        async with get_session() as session:
            stmt = select(WeiboNoteComment).where(WeiboNoteComment.comment_id == comment_id)
            res = await session.execute(stmt)
            db_comment = res.scalar_one_or_none()
            if db_comment:
                # 更新已存在的记录：只更新非主键字段
                db_comment.last_modify_ts = utils.get_current_timestamp()
                # 定义主键字段和不应更新的字段
                primary_key_fields = {'id'}  # 主键字段
                excluded_fields = {'add_ts'}  # 不应更新的字段（只在创建时设置）
                
                for key, value in comment_item.items():
                    # 跳过主键字段和不应更新的字段
                    if key in primary_key_fields or key in excluded_fields:
                        continue
                    # 只更新存在的字段
                    if hasattr(db_comment, key):
                        setattr(db_comment, key, value)
            else:
                # 创建新记录
                comment_item["add_ts"] = utils.get_current_timestamp()
                comment_item["last_modify_ts"] = utils.get_current_timestamp()
                db_comment = WeiboNoteComment(**comment_item)
                session.add(db_comment)
            await session.commit()

    async def store_creator(self, creator: Dict):
        """
        Weibo creator DB storage implementation
        Args:
            creator:

        Returns:

        """
        user_id = creator.get("user_id")
        async with get_session() as session:
            stmt = select(WeiboCreator).where(WeiboCreator.user_id == user_id)
            res = await session.execute(stmt)
            db_creator = res.scalar_one_or_none()
            if db_creator:
                # 更新已存在的记录：只更新非主键字段
                db_creator.last_modify_ts = utils.get_current_timestamp()
                # 定义主键字段和不应更新的字段
                primary_key_fields = {'id'}  # 主键字段
                excluded_fields = {'add_ts'}  # 不应更新的字段（只在创建时设置）
                
                for key, value in creator.items():
                    # 跳过主键字段和不应更新的字段
                    if key in primary_key_fields or key in excluded_fields:
                        continue
                    # 只更新存在的字段
                    if hasattr(db_creator, key):
                        setattr(db_creator, key, value)
            else:
                # 创建新记录
                creator["add_ts"] = utils.get_current_timestamp()
                creator["last_modify_ts"] = utils.get_current_timestamp()
                creator["note_count"] = 0
                db_creator = WeiboCreator(**creator)
                session.add(db_creator)
            await _sync_weibo_creator_note_count(session, int(user_id))
            await session.commit()


class WeiboJsonStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="weibo", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """
        content JSON storage implementation
        Args:
            content_item:

        Returns:

        """
        await self.writer.write_single_item_to_json(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        comment JSON storage implementation
        Args:
            comment_item:

        Returns:

        """
        await self.writer.write_single_item_to_json(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        """
        creator JSON storage implementation
        Args:
            creator:

        Returns:

        """
        await self.writer.write_single_item_to_json(item_type="creators", item=creator)


class WeiboSqliteStoreImplement(WeiboDbStoreImplement):
    """
    Weibo content SQLite storage implementation
    """
    pass


class WeiboSupabaseStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._warned_comment_unsupported = False

    @staticmethod
    def _build_rest_note_row(content_item: Dict) -> Dict:
        note_dt = content_item["create_date_time"]
        return {
            "note_id": int(content_item["note_id"]),
            "content": content_item["content"],
            "post_date": note_dt,
            "liked_count": int(content_item["liked_count"]),
            "comments_count": int(content_item["comments_count"]),
            "shared_count": int(content_item["shared_count"]),
            "last_modify_ts": int(content_item["last_modify_ts"]),
            "note_url": content_item["note_url"],
            "ip_location": content_item.get("ip_location") or None,
            "image_list": WeiboSupabaseStoreImplement._parse_image_list(content_item.get("image_list", "")),
            "user_id": int(content_item["user_id"]),
            "nickname": content_item["nickname"],
            "gender": content_item["gender"],
            "profile_url": content_item["profile_url"],
        }

    @staticmethod
    def _build_image_rows(content_item: Dict) -> list[Dict]:
        return build_weibo_image_rows(
            note_id=int(content_item["note_id"]),
            image_urls=WeiboSupabaseStoreImplement._parse_image_list(content_item.get("image_list", "")),
        )

    @staticmethod
    def _build_rest_creator_row(creator: Dict) -> Dict:
        last_modify_ts = int(creator.get("last_modify_ts") or utils.get_current_timestamp())
        return {
            "user_id": int(creator["user_id"]),
            "nickname": creator.get("nickname", "") or "",
            "gender": creator.get("gender", "") or "",
            "avatar": creator.get("avatar", "") or "",
            "desc": creator.get("desc") or None,
            "ip_location": creator.get("ip_location") or None,
            "follows": int(creator.get("follows") or 0),
            "fans": creator.get("fans", "") or "",
            "tag_list": creator.get("tag_list") or None,
            "last_modify_ts": last_modify_ts,
        }

    @staticmethod
    def _build_rest_creator_stub_from_note(content_item: Dict) -> Dict:
        return {
            "user_id": int(content_item["user_id"]),
            "nickname": content_item.get("nickname", "") or "",
            "gender": content_item.get("gender", "") or "",
            "avatar": content_item.get("avatar", "") or "",
            "desc": None,
            "ip_location": content_item.get("ip_location") or None,
            "follows": 0,
            "fans": "",
            "tag_list": None,
            "last_modify_ts": int(content_item["last_modify_ts"]),
        }

    async def _rest_upsert_note(self, content_item: Dict):
        await SupabaseWeiboRestStore.upsert(
            table_name="weibo_creators",
            conflict_field="user_id",
            row=self._build_rest_creator_stub_from_note(content_item),
        )
        await SupabaseWeiboRestStore.upsert(
            table_name="weibo_notes",
            conflict_field="note_id",
            row=self._build_rest_note_row(content_item),
        )
        try:
            await self._rest_sync_note_images(content_item)
        except Exception as exc:
            utils.logger.warning(
                f"[WeiboSupabaseStoreImplement._rest_upsert_note] "
                f"note upsert succeeded but image sync failed for note_id={content_item['note_id']}: {exc}"
            )

    async def _rest_upsert_creator(self, creator: Dict):
        creator_row = self._build_rest_creator_row(creator)
        await SupabaseWeiboRestStore.upsert(
            table_name="weibo_creators",
            conflict_field="user_id",
            row={**creator_row, "note_count": int(creator.get("note_count") or 0)},
        )

    @staticmethod
    def _parse_note_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @staticmethod
    def _parse_rfc2822_datetime(value: str):
        if not value:
            return None
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")

    @staticmethod
    def _parse_image_list(value: str):
        if not value:
            return []
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("image_list must be a JSON array")
        return parsed

    async def _sync_note_images(self, session: AsyncSession, content_item: Dict):
        note_id = int(content_item["note_id"])
        desired_rows = self._build_image_rows(content_item)
        result = await session.execute(
            select(SupabaseWeiboImage).where(SupabaseWeiboImage.note_id == note_id)
        )
        existing_rows = list(result.scalars())
        existing_by_index = {}
        duplicate_rows = []

        for existing_row in existing_rows:
            current = existing_by_index.get(existing_row.image_index)
            if current is None:
                existing_by_index[existing_row.image_index] = existing_row
                continue
            duplicate_rows.append(existing_row)

        for duplicate_row in duplicate_rows:
            await session.delete(duplicate_row)

        desired_by_index = {row["image_index"]: row for row in desired_rows}
        for image_index, row in desired_by_index.items():
            existing_row = existing_by_index.get(image_index)
            if existing_row is None:
                session.add(
                    SupabaseWeiboImage(
                        note_id=note_id,
                        image_url=row["image_url"],
                        image_index=image_index,
                    )
                )
                continue
            if existing_row.image_url != row["image_url"]:
                existing_row.image_url = row["image_url"]

        stale_indexes = set(existing_by_index.keys()) - set(desired_by_index.keys())
        for image_index in stale_indexes:
            await session.delete(existing_by_index[image_index])

    async def _rest_sync_note_images(self, content_item: Dict):
        note_id = int(content_item["note_id"])
        desired_rows = self._build_image_rows(content_item)
        existing_rows = await SupabaseWeiboRestStore.fetch_rows(
            table_name="weibo_images",
            select_fields="id,image_index,image_url",
            filters={"note_id": f"eq.{note_id}"},
            order_by="id.asc",
        )
        sync_plan = plan_weibo_image_upserts(
            existing_rows=existing_rows,
            desired_rows=desired_rows,
        )
        stale_ids = sync_plan["stale_ids"]

        if stale_ids:
            ids_sql = ",".join(str(row_id) for row_id in sorted(set(stale_ids)))
            await SupabaseWeiboRestStore.delete_rows(
                table_name="weibo_images",
                filters={"id": f"in.({ids_sql})"},
            )

        try:
            await SupabaseWeiboRestStore.upsert_many(
                table_name="weibo_images",
                conflict_field="note_id,image_index",
                rows=sync_plan["upsert_rows"],
            )
        except Exception as exc:
            utils.logger.warning(
                f"[WeiboSupabaseStoreImplement._rest_sync_note_images] "
                f"upsert failed for note_id={note_id}, fallback to delete+insert: {exc}"
            )
            await SupabaseWeiboRestStore.delete_rows(
                table_name="weibo_images",
                filters={"note_id": f"eq.{note_id}"},
            )
            if sync_plan["upsert_rows"]:
                await SupabaseWeiboRestStore._request(
                    method="POST",
                    table_name="weibo_images",
                    json_body=sync_plan["upsert_rows"],
                    prefer="return=minimal",
                )

    async def _ensure_creator_stub(self, session: AsyncSession, content_item: Dict):
        user_id = int(content_item["user_id"])
        db_creator = await session.get(SupabaseWeiboCreator, user_id)
        if db_creator:
            return db_creator

        db_creator = SupabaseWeiboCreator(
            user_id=user_id,
            nickname=content_item.get("nickname", "") or "",
            gender=content_item.get("gender", "") or "",
            avatar=content_item.get("avatar", "") or "",
            desc=None,
            ip_location=content_item.get("ip_location") or None,
            follows=0,
            fans="",
            tag_list=None,
            note_count=0,
            last_modify_ts=int(content_item["last_modify_ts"]),
        )
        session.add(db_creator)
        await session.flush()
        return db_creator

    async def _refresh_creator_note_count_db(self, session: AsyncSession, user_id: int):
        result = await session.execute(
            select(func.count()).select_from(SupabaseWeiboNote).where(SupabaseWeiboNote.user_id == user_id)
        )
        note_count = int(result.scalar_one() or 0)
        db_creator = await session.get(SupabaseWeiboCreator, user_id)
        if db_creator:
            db_creator.note_count = note_count
            db_creator.last_modify_ts = int(utils.get_current_timestamp())
        return note_count

    async def _refresh_creator_note_count_rest(self, user_id: int, last_modify_ts: int):
        note_rows = await SupabaseWeiboRestStore.fetch_rows(
            table_name="weibo_notes",
            select_fields="note_id",
            filters={"user_id": f"eq.{user_id}"},
        )
        note_count = len(note_rows)
        await SupabaseWeiboRestStore.upsert(
            table_name="weibo_creators",
            conflict_field="user_id",
            row={
                "user_id": user_id,
                "nickname": "",
                "gender": "",
                "avatar": "",
                "desc": None,
                "ip_location": None,
                "follows": 0,
                "fans": "",
                "tag_list": None,
                "note_count": note_count,
                "last_modify_ts": last_modify_ts,
            },
        )
        return note_count

    async def store_content(self, content_item: Dict):
        note_id = int(content_item["note_id"])
        user_id = int(content_item["user_id"])
        image_count = len(self._parse_image_list(content_item.get("image_list", "")))
        utils.logger.info(
            f"[WeiboSupabaseStoreImplement.store_content] begin upsert note_id={note_id}, user_id={user_id}, image_count={image_count}"
        )
        try:
            async with get_supabase_session() as session:
                await self._ensure_creator_stub(session, content_item)

                db_note = await session.get(SupabaseWeiboNote, note_id)
                note_dt = self._parse_note_datetime(content_item["create_date_time"])
                if db_note:
                    db_note.content = content_item["content"]
                    db_note.post_date = note_dt
                    db_note.liked_count = int(content_item["liked_count"])
                    db_note.comments_count = int(content_item["comments_count"])
                    db_note.shared_count = int(content_item["shared_count"])
                    db_note.last_modify_ts = int(content_item["last_modify_ts"])
                    db_note.note_url = content_item["note_url"]
                    db_note.ip_location = content_item.get("ip_location") or None
                    db_note.image_list = self._parse_image_list(content_item.get("image_list", ""))
                    db_note.user_id = int(content_item["user_id"])
                    db_note.nickname = content_item["nickname"]
                    db_note.gender = content_item["gender"]
                    db_note.profile_url = content_item["profile_url"]
                else:
                    session.add(
                        SupabaseWeiboNote(
                            note_id=note_id,
                            content=content_item["content"],
                            post_date=note_dt,
                            liked_count=int(content_item["liked_count"]),
                            comments_count=int(content_item["comments_count"]),
                            shared_count=int(content_item["shared_count"]),
                            last_modify_ts=int(content_item["last_modify_ts"]),
                            note_url=content_item["note_url"],
                            ip_location=content_item.get("ip_location") or None,
                            image_list=self._parse_image_list(content_item.get("image_list", "")),
                            user_id=int(content_item["user_id"]),
                            nickname=content_item["nickname"],
                            gender=content_item["gender"],
                            profile_url=content_item["profile_url"],
                        )
                    )
                await self._sync_note_images(session, content_item)
                await self._refresh_creator_note_count_db(session, user_id)
            utils.logger.info(
                f"[WeiboSupabaseStoreImplement.store_content] stored via db session note_id={note_id}, user_id={user_id}, image_count={image_count}"
            )
        except Exception as exc:
            utils.logger.warning(
                f"[WeiboSupabaseStoreImplement.store_content] DB session unavailable, fallback to REST upsert for note {note_id}: {exc}"
            )
            await self._rest_upsert_note(content_item)
            await self._refresh_creator_note_count_rest(user_id, int(content_item["last_modify_ts"]))
            utils.logger.info(
                f"[WeiboSupabaseStoreImplement.store_content] stored via REST note_id={note_id}, user_id={user_id}, image_count={image_count}"
            )

    async def store_comment(self, comment_item: Dict):
        if not self._warned_comment_unsupported:
            utils.logger.warning(
                "[WeiboSupabaseStoreImplement.store_comment] Supabase store currently does not persist weibo comments."
            )
            self._warned_comment_unsupported = True

    async def store_creator(self, creator: Dict):
        user_id = int(creator["user_id"])
        last_modify_ts = int(creator.get("last_modify_ts") or utils.get_current_timestamp())
        creator_row = {
            **creator,
            "last_modify_ts": last_modify_ts,
        }
        utils.logger.info(
            f"[WeiboSupabaseStoreImplement.store_creator] begin upsert creator user_id={user_id}"
        )
        try:
            async with get_supabase_session() as session:
                db_creator = await session.get(SupabaseWeiboCreator, user_id)
                if db_creator:
                    db_creator.nickname = creator_row.get("nickname", "") or ""
                    db_creator.gender = creator_row.get("gender", "") or ""
                    db_creator.avatar = creator_row.get("avatar", "") or ""
                    db_creator.desc = creator_row.get("desc") or None
                    db_creator.ip_location = creator_row.get("ip_location") or None
                    db_creator.follows = int(creator_row.get("follows") or 0)
                    db_creator.fans = creator_row.get("fans", "") or ""
                    db_creator.tag_list = creator_row.get("tag_list") or None
                    db_creator.note_count = int(creator_row.get("note_count") or 0)
                    db_creator.last_modify_ts = last_modify_ts
                else:
                    session.add(
                        SupabaseWeiboCreator(
                            user_id=user_id,
                            nickname=creator_row.get("nickname", "") or "",
                            gender=creator_row.get("gender", "") or "",
                            avatar=creator_row.get("avatar", "") or "",
                            desc=creator_row.get("desc") or None,
                            ip_location=creator_row.get("ip_location") or None,
                            follows=int(creator_row.get("follows") or 0),
                            fans=creator_row.get("fans", "") or "",
                            tag_list=creator_row.get("tag_list") or None,
                            note_count=int(creator_row.get("note_count") or 0),
                            last_modify_ts=last_modify_ts,
                        )
                    )
            utils.logger.info(
                f"[WeiboSupabaseStoreImplement.store_creator] stored via db session creator user_id={user_id}"
            )
        except Exception as exc:
            utils.logger.warning(
                f"[WeiboSupabaseStoreImplement.store_creator] DB session unavailable, fallback to REST upsert for creator {user_id}: {exc}"
            )
            await self._rest_upsert_creator(creator)
            await self._refresh_creator_note_count_rest(user_id, last_modify_ts)
            utils.logger.info(
                f"[WeiboSupabaseStoreImplement.store_creator] stored via REST creator user_id={user_id}"
            )
