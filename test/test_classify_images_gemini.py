# -*- coding: utf-8 -*-

import types
from io import StringIO
from unittest.mock import patch

import classify_images_gemini as module


def test_build_where_clause_respects_force_flag():
    assert module.build_where_clause(force=False) == "(is_commercial IS NULL OR is_selfie IS NULL)"
    assert module.build_where_clause(force=True) == "TRUE"


def test_parse_supabase_rows_json_payload():
    raw = '{"boundary":"x","rows":[{"id":123,"image_url":"https://img.example/1.jpg"}],"warning":"w"}'
    rows = module.parse_table_rows(raw)
    assert rows == [{"id": 123, "image_url": "https://img.example/1.jpg"}]


def test_count_rows_supports_supabase_json_payload():
    payload = '{"boundary":"x","rows":[{"count":30085}],"warning":"w"}'
    with patch.object(module, "db_query", return_value=payload):
        assert module.count_rows(force=False) == 30085


def test_build_update_sql_updates_both_flags_without_classified_at():
    sql = module.build_update_sql(
        [
            {"id": 1, "is_commercial": True, "is_selfie": False},
            {"id": 2, "is_commercial": False, "is_selfie": True},
        ]
    )

    assert "is_commercial = CASE id WHEN 1 THEN true WHEN 2 THEN false END" in sql
    assert "is_selfie = CASE id WHEN 1 THEN false WHEN 2 THEN true END" in sql
    assert "classified_at" not in sql


def test_normalize_result_forces_selfie_false_when_commercial():
    assert module.normalize_result({"is_commercial": True, "is_selfie": True}) == {
        "is_commercial": True,
        "is_selfie": False,
    }
    assert module.normalize_result({"is_commercial": False, "is_selfie": True}) == {
        "is_commercial": False,
        "is_selfie": True,
    }


def test_normalize_result_coerces_string_bools():
    assert module.normalize_result({"is_commercial": "false", "is_selfie": "true"}) == {
        "is_commercial": False,
        "is_selfie": True,
    }


def test_parse_response_prefers_structured_output():
    response = types.SimpleNamespace(
        parsed=types.SimpleNamespace(is_commercial=False, is_selfie=True),
        text='{"is_commercial": true, "is_selfie": false}',
    )

    assert module.parse_response(response) == {
        "is_commercial": False,
        "is_selfie": True,
    }


def test_parse_response_falls_back_to_json_text():
    response = types.SimpleNamespace(parsed=None, text='{"is_commercial": true, "is_selfie": true}')

    assert module.parse_response(response) == {
        "is_commercial": True,
        "is_selfie": False,
    }


def test_classify_one_uses_gemini_and_normalizes_output():
    fake_response = types.SimpleNamespace(
        parsed=types.SimpleNamespace(is_commercial=True, is_selfie=True),
        text="",
    )
    fake_client = types.SimpleNamespace(
        models=types.SimpleNamespace(
            generate_content=lambda **kwargs: fake_response,
        )
    )

    with patch.object(module, "download_and_resize", return_value=b"image-bytes"):
        result = module.classify_one(fake_client, {"id": 7, "image_url": "https://img.example/1.jpg"})

    assert result == {"id": 7, "is_commercial": True, "is_selfie": False}


def test_classify_url_downloads_and_classifies_once():
    fake_client = object()
    with patch.object(module, "download_and_resize", return_value=b"image-bytes"), patch.object(
        module, "classify_image", return_value={"is_commercial": False, "is_selfie": True}
    ) as classify_image:
        result = module.classify_url(fake_client, "https://img.example/1.jpg")

    assert result == {"is_commercial": False, "is_selfie": True}
    classify_image.assert_called_once_with(fake_client, b"image-bytes")


def test_emit_single_result_csv_writes_two_columns():
    buffer = StringIO()
    with patch("sys.stdout", buffer):
        module.emit_single_result({"is_commercial": True, "is_selfie": False}, "csv")

    assert buffer.getvalue() == "is_commercial,is_selfie\r\ntrue,false\r\n"


def test_emit_single_result_json_writes_json():
    buffer = StringIO()
    with patch("sys.stdout", buffer):
        module.emit_single_result({"is_commercial": True, "is_selfie": False}, "json")

    assert buffer.getvalue().strip() == '{"is_commercial": true, "is_selfie": false}'


def test_classify_image_passes_expected_sdk_config():
    captured = {}

    def fake_generate_content(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            parsed=types.SimpleNamespace(is_commercial=False, is_selfie=True),
            text="",
        )

    fake_client = types.SimpleNamespace(
        models=types.SimpleNamespace(generate_content=fake_generate_content)
    )

    result = module.classify_image(fake_client, b"image-bytes")

    assert result == {"is_commercial": False, "is_selfie": True}
    assert captured["model"] == module.MODEL
    assert captured["contents"][0] == module.PROMPT
    assert captured["contents"][1].inline_data.mime_type == "image/jpeg"
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_schema is module.GeminiClassification


def test_classify_image_falls_back_to_rest_on_sdk_error():
    def raise_timeout(**kwargs):
        raise TimeoutError("sdk timeout")

    fake_client = types.SimpleNamespace(
        models=types.SimpleNamespace(generate_content=raise_timeout)
    )

    with patch.object(
        module, "classify_image_rest", return_value={"is_commercial": False, "is_selfie": True}
    ) as rest_call:
        result = module.classify_image(fake_client, b"image-bytes")

    assert result == {"is_commercial": False, "is_selfie": True}
    rest_call.assert_called_once_with(b"image-bytes")


def test_load_api_key_prefers_env_over_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=file-value\n", encoding="utf-8")

    monkeypatch.setattr(module, "ENV_FILE", env_file)
    monkeypatch.setenv("GEMINI_API_KEY", "env-value")

    assert module.load_api_key() == "env-value"


def test_load_api_key_falls_back_to_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_KEY=1\nGEMINI_API_KEY=file-value\n", encoding="utf-8")

    monkeypatch.setattr(module, "ENV_FILE", env_file)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert module.load_api_key() == "file-value"
