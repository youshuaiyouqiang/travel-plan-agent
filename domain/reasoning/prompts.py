"""推理引擎使用的提示词常量。

P6.1 从 ``engine.py`` 拆出：将大型提示词模板独立为模块常量，
降低 engine.py 行数并便于后续维护。
"""

from __future__ import annotations


REACT_SYSTEM_SUFFIX = """You MUST return exactly one of the following two formats.

Format 1 - Final answer (plain text only):
Return just the plain text response for the user. No JSON, no tags, no code blocks.
Do NOT wrap your answer in a JSON object like {{"text": "..."}}. Just write the answer directly.
Your final answer MUST be natural language that the user can read directly.

CRITICAL RULES for Format 1:
- NEVER include your internal reasoning, planning, or thinking process in the final answer.
- Do NOT write things like "Now I have enough information", "Let me compile", "Key findings:", "Let me now", "I will now", etc.
- The final answer should be a polished, direct response to the user — as if a human expert wrote it.
- You MUST write in the SAME LANGUAGE as the user's message. If the user writes in Chinese, your final answer MUST be in Chinese.
- Do NOT mix English reasoning with Chinese content. The entire final answer must be in the user's language.

Format 2 - Tool calls (JSON only, NO XML):
{{
  "tool_calls": [
    {{"name": "tool_name", "arguments": {{"arg": "value"}}}}
  ],
  "text": "optional short note"
}}

CRITICAL RULES for Format 2:
- The JSON MUST start with {{ and end with }}. Do NOT omit the opening or closing braces.
- Do NOT add any text before or after the JSON object.
- Do NOT use XML tags like <tool_call/>. Use ONLY the JSON format shown above.
- Each tool call MUST have both "name" and "arguments" keys.

IMPORTANT: NEVER use XML tags. Always use the JSON format above.
If you need tools, return ONLY the JSON object, no text before or after it.
Only use JSON when you actually need to call tools.
When you have enough tool results, you MUST switch to Format 1 (plain text).
NEVER return JSON as your final answer to the user.
"""
