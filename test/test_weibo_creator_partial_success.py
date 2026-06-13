# -*- coding: utf-8 -*-

import asyncio
from types import SimpleNamespace

import pytest

import config
from media_platform.weibo.client import WeiboClient
from store import weibo as weibo_store
from store.weibo._store_impl import WeiboDbStoreImplement


def test_get_all_notes_by_creator_id_preserves_previous_pages_when_callback_fails(monkeypatch):
    client = WeiboClient.__new__(WeiboClient)
    created_at = "Wed May 29 23:59:22 +0800 2024"
    responses = [
        {
            "cards": [
                {
                    "mblog": {
                        "id": "note_1",
                        "created_at": created_at,
                    }
                }
            ],
            "cardlistInfo": {
                "since_id": "page_2",
                "total": 20,
            },
        },
        {
            "cards": [
                {
                    "mblog": {
                        "id": "note_2",
                        "created_at": created_at,
                    }
                }
            ],
            "cardlistInfo": {
                "since_id": "0",
                "total": 20,
            },
        },
    ]

    async def fake_get_notes_by_creator(creator, container_id, since_id="0", page=None):
        return responses.pop(0)

    async def fake_sleep(_seconds):
        return None

    callback_calls = []

    async def flaky_callback(notes):
        callback_calls.append([note["mblog"]["id"] for note in notes])
        if len(callback_calls) == 2:
            raise RuntimeError("simulated store failure")
        return {"received": len(notes), "stored": len(notes), "failed": 0}

    monkeypatch.setattr(client, "get_notes_by_creator", fake_get_notes_by_creator)
    monkeypatch.setattr("media_platform.weibo.client.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("media_platform.weibo.client.random.uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(config, "WEIBO_CREATOR_SINCE_DATE", "2010-01-01")

    result = asyncio.run(
        client.get_all_notes_by_creator_id(
            creator_id="123",
            container_id="container",
            crawl_interval=0,
            callback=flaky_callback,
            max_retries=0,
            retry_delay=0,
        )
    )

    assert [note["mblog"]["id"] for note in result] == ["note_1"]
    assert callback_calls == [["note_1"], ["note_2"]]


def test_batch_update_weibo_notes_keeps_processing_after_single_failure(monkeypatch):
    calls = []

    async def fake_update_weibo_note(note_item):
        note_id = note_item["mblog"]["id"]
        calls.append(note_id)
        if note_id == "bad_note":
            raise ValueError("simulated single note failure")

    monkeypatch.setattr(weibo_store, "update_weibo_note", fake_update_weibo_note)

    summary = asyncio.run(
        weibo_store.batch_update_weibo_notes(
            [
                {"mblog": {"id": "good_note_1"}},
                {"mblog": {"id": "bad_note"}},
                {"mblog": {"id": "good_note_2"}},
            ]
        )
    )

    assert calls == ["good_note_1", "bad_note", "good_note_2"]
    assert summary == {"received": 3, "stored": 2, "failed": 1}


def test_batch_update_weibo_notes_raises_when_all_notes_fail(monkeypatch):
    async def always_fail(_note_item):
        raise ValueError("all failed")

    monkeypatch.setattr(weibo_store, "update_weibo_note", always_fail)

    with pytest.raises(ValueError, match="all failed"):
        asyncio.run(
            weibo_store.batch_update_weibo_notes(
                [
                    {"mblog": {"id": "bad_note_1"}},
                    {"mblog": {"id": "bad_note_2"}},
                ]
            )
        )


def test_weibo_db_store_updates_creator_note_count(monkeypatch):
    store = WeiboDbStoreImplement()
    creator = SimpleNamespace(note_count=0, last_modify_ts=0)
    note = SimpleNamespace(last_modify_ts=0)

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalar_one(self):
            return self._value

    class FakeSession:
        def __init__(self):
            self.calls = 0
            self.committed = False

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return FakeResult(note)
            if self.calls == 2:
                return FakeResult(3)
            if self.calls == 3:
                return FakeResult(creator)
            raise AssertionError("unexpected execute call")

        async def commit(self):
            self.committed = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_session = FakeSession()
    monkeypatch.setattr("store.weibo._store_impl.get_session", lambda: FakeContext(fake_session))
    monkeypatch.setattr("store.weibo._store_impl.utils.get_current_timestamp", lambda: 1234567890)

    asyncio.run(
        store.store_content(
            {
                "note_id": 1001,
                "user_id": "42",
                "content": "hello",
                "create_time": 1,
                "create_date_time": "2024-01-01 00:00:00",
                "liked_count": "0",
                "comments_count": "0",
                "shared_count": "0",
                "last_modify_ts": 123,
                "note_url": "https://example.com",
                "ip_location": "",
                "image_list": "",
                "nickname": "n",
                "gender": "m",
                "profile_url": "p",
                "avatar": "a",
                "source_keyword": "",
            }
        )
    )

    assert creator.note_count == 3
    assert creator.last_modify_ts == 1234567890
    assert fake_session.committed is True
