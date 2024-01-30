#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/1/4 19:07
# @Author  : alexanderwu
# @File    : mermaid_config.py

from typing import Literal

from metagpt.utils.yaml_model import YamlModel


class MermaidConfig(YamlModel):
    """Config for Mermaid"""

    engine: Literal["nodejs", "ink", "playwright", "pyppeteer"] = "nodejs"
    path: str = ""
    puppeteer_config: str = ""  # Only for nodejs engine
