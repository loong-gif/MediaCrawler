# -*- coding: utf-8 -*-

import asyncio
import sys

import config

from cmd_arg.arg import parse_cmd


def test_parse_cmd_overrides_weibo_creator_since_date(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--weibo_creator_since_date",
            "2010-01-01",
        ],
    )
    monkeypatch.setattr(config, "WEIBO_CREATOR_SINCE_DATE", "")

    args = asyncio.run(parse_cmd())

    assert args.weibo_creator_since_date == "2010-01-01"
    assert config.WEIBO_CREATOR_SINCE_DATE == "2010-01-01"
