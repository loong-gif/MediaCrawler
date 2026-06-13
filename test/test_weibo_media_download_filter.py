# -*- coding: utf-8 -*-

import asyncio
from unittest.mock import patch

import classify_images_gemini as classify_module
from config import base_config
from store import weibo as weibo_store
from tools import download_weibo_media_from_supabase as download_module


def test_sanitize_weibo_media_filename_replaces_spaces_and_invalid_chars():
    assert weibo_store.sanitize_weibo_media_filename("a b/c:*d") == "a_b_c_d"


def test_build_weibo_selfie_image_filename_uses_underscores():
    assert weibo_store.build_weibo_selfie_image_filename(note_id=12345, image_index=7) == "12345_7"


def test_should_download_classified_selfies_respects_filter(monkeypatch):
    monkeypatch.setattr(base_config, "ENABLE_GET_MEIDAS", True)
    monkeypatch.setattr(base_config, "WEIBO_MEDIA_DOWNLOAD_FILTER", "is_selfie_true")
    assert classify_module.should_download_classified_selfies() is True

    monkeypatch.setattr(base_config, "WEIBO_MEDIA_DOWNLOAD_FILTER", "all")
    assert classify_module.should_download_classified_selfies() is False


def test_build_selfie_download_rows_only_keeps_true_selfies():
    rows = classify_module.build_selfie_download_rows(
        [
            {
                "id": 1,
                "note_id": 100,
                "image_index": 1,
                "image_url": "https://img.example/1.jpg",
                "is_selfie": True,
            },
            {
                "id": 2,
                "note_id": 100,
                "image_index": 2,
                "image_url": "https://img.example/2.jpg",
                "is_selfie": False,
            },
            {
                "id": 3,
                "note_id": 100,
                "image_index": 3,
                "image_url": "",
                "is_selfie": True,
            },
        ]
    )

    assert rows == [
        {
            "note_id": 100,
            "image_index": 1,
            "image_url": "https://img.example/1.jpg",
        }
    ]


def test_download_selfie_media_rows_uses_note_id_and_image_index():
    captured = []

    async def fake_download(image_url: str, save_path: str, filename: str) -> bool:
        captured.append((image_url, save_path, filename))
        return True

    with patch.object(classify_module, "download_weibo_image", side_effect=fake_download):
        success_count, total_count = classify_module.download_selfie_media_rows(
            [
                {
                    "note_id": 200,
                    "image_index": 3,
                    "image_url": "https://img.example/3.jpg",
                }
            ]
        )

    assert (success_count, total_count) == (1, 1)
    assert captured == [("https://img.example/3.jpg", "data/weibo/images", "200_3")]


def test_update_weibo_note_skips_crawl_time_download_when_filter_is_selfie_true(monkeypatch):
    captured_items = []

    class DummyStore:
        async def store_content(self, content_item):
            captured_items.append(content_item)

    async def fail_download(*args, **kwargs):
        raise AssertionError("download should not be called")

    monkeypatch.setattr(base_config, "ENABLE_GET_MEIDAS", True)
    monkeypatch.setattr(base_config, "WEIBO_MEDIA_DOWNLOAD_FILTER", "is_selfie_true")

    note_item = {
        "mblog": {
            "id": "123",
            "text": "自拍内容",
            "created_at": "Thu Oct 26 01:21:33 +0800 2023",
            "attitudes_count": 1,
            "comments_count": 2,
            "reposts_count": 3,
            "region_name": "发布于 上海",
            "pics": [{"url": "https://wx1.sinaimg.cn/large/test.jpg"}],
            "user": {
                "id": "9",
                "screen_name": "Name With Space",
                "gender": "f",
                "profile_url": "https://m.weibo.cn/u/9",
                "profile_image_url": "https://img.example/avatar.jpg",
            },
        }
    }

    with patch.object(weibo_store.WeibostoreFactory, "create_store", return_value=DummyStore()), patch.object(
        weibo_store, "download_weibo_image", side_effect=fail_download
    ):
        asyncio.run(weibo_store.update_weibo_note(note_item))

    assert len(captured_items) == 1
    assert "https://wx1.sinaimg.cn/large/test.jpg" in captured_items[0]["image_list"]


def test_update_weibo_note_downloads_immediately_when_filter_is_all(monkeypatch):
    captured_downloads = []

    class DummyStore:
        async def store_content(self, content_item):
            return None

    async def fake_download(image_url: str, save_path: str, filename: str) -> bool:
        captured_downloads.append((image_url, save_path, filename))
        return True

    monkeypatch.setattr(base_config, "ENABLE_GET_MEIDAS", True)
    monkeypatch.setattr(base_config, "WEIBO_MEDIA_DOWNLOAD_FILTER", "all")

    note_item = {
        "mblog": {
            "id": "124",
            "text": "content with space",
            "created_at": "Thu Oct 26 01:21:33 +0800 2023",
            "attitudes_count": 1,
            "comments_count": 2,
            "reposts_count": 3,
            "region_name": "发布于 上海",
            "pics": [{"url": "https://wx1.sinaimg.cn/large/test.jpg"}],
            "user": {
                "id": "10",
                "screen_name": "Name With Space",
                "gender": "f",
                "profile_url": "https://m.weibo.cn/u/10",
                "profile_image_url": "https://img.example/avatar.jpg",
            },
        }
    }

    with patch.object(weibo_store.WeibostoreFactory, "create_store", return_value=DummyStore()), patch.object(
        weibo_store, "download_weibo_image", side_effect=fake_download
    ):
        asyncio.run(weibo_store.update_weibo_note(note_item))

    assert len(captured_downloads) == 1
    assert captured_downloads[0][1] == "data/weibo/images"
    assert " " not in captured_downloads[0][2]


def test_download_weibo_media_from_supabase_uses_only_selfie_rows():
    rows = [
        {"note_id": 300, "image_index": 1, "image_url": "https://img.example/1.jpg"}
    ]

    async def fake_fetch_selfie_rows(*, limit, offset):
        assert limit == 50
        if offset == 0:
            return rows
        return []

    async def fake_download_rows(*, rows, save_path):
        assert rows == [
            {"note_id": 300, "image_index": 1, "image_url": "https://img.example/1.jpg"}
        ]
        assert save_path == "custom_dir"
        return 1, 1

    with patch.object(download_module, "fetch_selfie_rows", side_effect=fake_fetch_selfie_rows), patch.object(
        download_module, "download_rows", side_effect=fake_download_rows
    ):
        success_count, total_count = asyncio.run(
            download_module.run(save_path="custom_dir", batch_size=50)
        )

    assert (success_count, total_count) == (1, 1)
