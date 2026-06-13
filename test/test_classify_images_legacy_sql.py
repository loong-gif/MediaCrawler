# -*- coding: utf-8 -*-

import classify_images as async_module
import classify_images_openai as openai_module
import classify_images_sync as sync_module


def test_legacy_update_sql_does_not_reference_classified_at():
    captured_sql = []

    def capture(sql: str):
        captured_sql.append(sql)
        return ""

    updates = [{"id": 1, "is_commercial": True}]

    async_module.db_query = capture
    openai_module.db_query = capture
    sync_module.db_query = capture

    async_module.update_batch(updates)
    openai_module.update_batch(updates)
    sync_module.update_batch(updates)

    assert len(captured_sql) == 3
    assert all("classified_at" not in sql for sql in captured_sql)
