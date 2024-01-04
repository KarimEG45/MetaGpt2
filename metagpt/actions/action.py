#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/11 14:43
@Author  : alexanderwu
@File    : action.py
"""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import ConfigDict, Field,field_validator,model_validator
from metagpt.config import CONFIG,LLMProviderEnum
from metagpt.actions.action_node import ActionNode
from metagpt.llm import LLM
from metagpt.provider.base_llm import BaseLLM
from metagpt.schema import (
    CodeSummarizeContext,
    CodingContext,
    RunCodeContext,
    SerializationMixin,
    TestingContext,
)
from metagpt.logs import logger

class Action(SerializationMixin, is_polymorphic_base=True):
    model_config = ConfigDict(arbitrary_types_allowed=True, exclude=["llm"])

    name: str = ""
    #llm: BaseLLM = Field(default_factory=LLM, exclude=True)
    llm: BaseLLM = None
    type: str = ""
    #llm: BaseLLM = Field(default_factory=None, exclude=True)
    context: Union[dict, CodingContext, CodeSummarizeContext, TestingContext, RunCodeContext, str, None] = ""
    prefix: str = ""  # aask*时会加上prefix，作为system_message
    desc: str = ""  # for skill manager
    node: ActionNode = Field(default=None, exclude=True)

    @model_validator(mode="before")
    def select_llm(cls,self):
        llm_type = CONFIG._get(cls.__name__)
        logger.info(f"Action : {cls.__name__} will use configuration as follow")

        if llm_type:
            self['llm'] = LLM(LLMProviderEnum(llm_type))
        else:
            self['llm'] = LLM()

        return self

    def __init_with_instruction(self, instruction: str):
        """Initialize action with instruction"""
        self.node = ActionNode(key=self.name, expected_type=str, instruction=instruction, example="", schema="raw")
        return self

    def __init__(self, **data: Any):


        super().__init__(**data)

        if "instruction" in data:
            self.__init_with_instruction(data["instruction"])


    def set_prefix(self, prefix):
        """Set prefix for later usage"""
        self.prefix = prefix
        self.llm.system_prompt = prefix
        if self.node:
            self.node.llm = self.llm
        return self

    def __str__(self):
        return self.__class__.__name__

    def __repr__(self):
        return self.__str__()

    async def _aask(self, prompt: str, system_msgs: Optional[list[str]] = None) -> str:
        """Append default prefix"""
        return await self.llm.aask(prompt, system_msgs)

    async def _run_action_node(self, *args, **kwargs):
        """Run action node"""
        msgs = args[0]
        context = "## History Messages\n"
        context += "\n".join([f"{idx}: {i}" for idx, i in enumerate(reversed(msgs))])
        return await self.node.fill(context=context, llm=self.llm)

    async def run(self, *args, **kwargs):
        """Run action"""
        if self.node:
            return await self._run_action_node(*args, **kwargs)
        raise NotImplementedError("The run method should be implemented in a subclass.")
