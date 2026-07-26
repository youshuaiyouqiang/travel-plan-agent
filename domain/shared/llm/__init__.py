"""LLM 端口与供应商无关的消息/响应类型。

P4.1 引入：将 ``OpenAILLM`` / ``FallbackLLM`` 的公共接口抽象为
``LLMPort`` Protocol，供 domain/application 层消费；具体 SDK 实现
（OpenAI、降级链）留在 ``infrastructure/llm/``。
"""
