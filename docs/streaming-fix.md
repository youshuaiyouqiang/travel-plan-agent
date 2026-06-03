# 流式输出 Bug 修复开发文档

## 问题描述

前端已接入 SSE 流式接口，但实际体验仍然是"等模型全部输出完才一次性显示"，只有一个光标在闪烁，没有逐字输出效果。

## 根因分析

`core/reasoning.py` 中的 `run_stream` 方法存在以下问题：

1. **所有 LLM 调用仍使用非流式 API**：`run_stream` 的循环体中，每一轮都调用 `complete_with_tools`（非流式），等模型完整返回后才进入下一轮逻辑。
2. **最终回复阶段的"流式"是假的**：当 `decision.decision_type == FINAL_ANSWER` 时，`decision.text` 已经是完整文本，代码只是把它切成小块 yield，前端瞬间收到所有文本，没有真正的逐 token 流式效果。

**关键矛盾**：工具调用阶段必须用非流式（需要完整返回才能解析 `tool_calls` JSON），但最终回复阶段应该用流式 API 逐 token 输出。

## 修复方案

### 核心思路

在 `run_stream` 的推理循环中，区分两种场景：

- **工具调用阶段**：继续使用 `complete_with_tools`（非流式），因为需要完整解析 tool_calls
- **最终回复阶段**：改用 `stream_complete`（真正的流式 API），逐 token yield 给前端

### 判断"最终回复阶段"的时机

当以下条件同时满足时，进入最终回复流式输出：

1. `tools_executed == True`（已经执行过工具调用，有了数据）
2. 上一轮刚执行完工具，working_messages 末尾包含 tool result
3. 模型不再需要调用工具，应该直接生成最终答案

具体实现：在工具结果追加到 working_messages 后，下一轮 LLM 调用改用 `stream_complete`（不传 tools schema），让模型直接流式输出纯文本。

### 需要修改的文件

仅 **1 个文件**：`core/reasoning.py`

前端代码、`core/agent.py`、`api/server.py`、`core/llm.py` 均无需改动。

---

## 详细修改步骤

### 步骤 1：重写 `run_stream` 方法

将 `core/reasoning.py` 中的 `run_stream` 方法替换为以下逻辑：

```python
async def run_stream(
    self, *, system_prompt: str, user_message: str, force_tool: bool
) -> AsyncGenerator[str, None]:
    """流式推理：工具调用阶段同步执行，最终回复阶段逐 token 流式输出。"""
    working_messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]
    self.last_trace = []
    no_tool_rounds = 0
    best_text = ""
    tools_executed = False
    seen_signatures: dict[str, int] = {}
    use_native = getattr(settings, "use_native_tool_calling", True)
    tools_schema = self._build_tools_schema() if use_native else None

    for iteration in range(1, settings.max_iterations + 1):
        logger.info("===== Reasoning stream iteration %s/%s =====", iteration, settings.max_iterations)
        near_limit = iteration >= settings.max_iterations - 2

        # ===== 关键判断：是否进入最终回复流式阶段 =====
        # 条件：已经执行过工具，且 working_messages 末尾是工具结果或催促回复的消息
        # 此时模型应该直接输出最终答案，不再需要调用工具
        should_stream_final = (
            tools_executed
            and not near_limit
            and len(working_messages) >= 3
            and any(
                msg.get("role") == "tool" or
                (msg.get("role") == "user" and "Use the tool results" in (msg.get("content") or ""))
                for msg in working_messages[-3:]
            )
        )

        if should_stream_final:
            # ===== 真正的流式输出：调用 stream_complete，不传 tools =====
            logger.info("Stream: entering final streaming phase at iteration %s", iteration)
            trace = TraceStep(
                iteration=iteration,
                decision_type="stream_final_answer",
                text="",
            )
            full_text = ""
            try:
                async for chunk in self._llm.stream_complete(
                    system=system_prompt,
                    messages=working_messages,
                ):
                    full_text += chunk
                    yield chunk
            except Exception as e:
                logger.warning("Stream final answer failed: %s, falling back", e)
                # 流式失败，回退到非流式
                fallback = await self._llm.complete(
                    system=system_prompt, messages=working_messages,
                )
                full_text = fallback
                yield fallback

            trace.text = full_text[:200]
            self._record_trace(trace)
            return

        # ===== 非流式阶段：正常调用 complete_with_tools =====
        if use_native and tools_schema:
            llm_resp = await self._llm.complete_with_tools(
                system=system_prompt,
                messages=working_messages,
                tools=tools_schema if not near_limit else None,
            )
            decision = self._llm_response_to_decision(llm_resp)
            if not decision.text and not decision.tool_calls:
                decision = self._parse_decision(llm_resp.content or "")
        else:
            response = await self._llm.complete(
                system=system_prompt + "\n\n" + REACT_SYSTEM_SUFFIX,
                messages=working_messages,
            )
            decision = self._parse_decision(response)

        logger.info(
            "Stream Decision: type=%s tool_calls=%s",
            decision.decision_type.value,
            [call.name for call in decision.tool_calls],
        )
        trace = TraceStep(
            iteration=iteration,
            decision_type=decision.decision_type.value,
            text=decision.text,
            tool_calls=[
                {"name": call.name, "arguments": call.arguments, "id": call.call_id}
                for call in decision.tool_calls
            ],
        )

        # ===== FINAL_ANSWER 但还没执行过工具 =====
        if decision.decision_type == DecisionType.FINAL_ANSWER:
            if len(decision.text) > len(best_text):
                best_text = decision.text

            # 如果还没执行工具但 force_tool，强制重试
            if force_tool and not tools_executed and no_tool_rounds < 2:
                no_tool_rounds += 1
                trace.system_note = "forced_retry_no_tools"
                working_messages.append({"role": "assistant", "content": decision.text})
                working_messages.append({
                    "role": "user",
                    "content": "You have not used tools yet. If the task requires action, call tools now. If the task truly needs no tools, provide a direct complete answer.",
                })
                self._record_trace(trace)
                continue

            # 没有工具调用，直接流式输出最终答案
            # 这种情况适用于：闲聊、简单问答等不需要工具的场景
            self._record_trace(trace)
            if decision.text.strip():
                # 尝试用流式 API 重新生成，获得真正的逐 token 输出
                try:
                    stream_text = ""
                    async for chunk in self._llm.stream_complete(
                        system=system_prompt,
                        messages=working_messages,
                    ):
                        stream_text += chunk
                        yield chunk
                    # 如果流式输出为空，回退到已有文本
                    if not stream_text.strip():
                        yield self._clean_final_answer(decision.text.strip())
                except Exception:
                    yield self._clean_final_answer(decision.text.strip())
            return

        # ===== 工具调用处理（与 run 方法相同）=====
        duplicate_round = False
        for call in decision.tool_calls:
            signature = self._make_signature(call)
            seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
            if seen_signatures[signature] >= 3:
                duplicate_round = True

        if duplicate_round:
            trace.system_note = "duplicate_tool_calls_detected"
            self._record_trace(trace)
            working_messages.append({"role": "assistant", "content": decision.text})
            working_messages.append({
                "role": "user",
                "content": "You are repeating the same tool call pattern. Use a different tool, ask the user for missing information, or provide the best final answer.",
            })
            continue

        if near_limit and decision.tool_calls:
            trace.system_note = "forced_final_answer_near_limit"
            self._record_trace(trace)
            working_messages.append({"role": "assistant", "content": decision.text or ""})
            working_messages.append({
                "role": "user",
                "content": "You are approaching the maximum number of reasoning steps. You MUST now provide a complete final answer. Do NOT call any more tools.",
            })
            continue

        tool_results = await self._tool_executor.execute(decision.tool_calls)
        tools_executed = True
        trace.tool_results = tool_results
        self._record_trace(trace)

        confirmation_required = [r for r in tool_results if r.get("requires_confirmation")]
        if confirmation_required:
            first = confirmation_required[0]
            raise ConfirmationNeeded(str(first.get("content") or "Confirmation required."))

        for result in tool_results:
            if result.get("ask_user"):
                raise AskUserNeeded(str(result.get("question") or result.get("content") or ""))

        # 将工具结果追加到 working_messages
        if use_native:
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": decision.text or None}
            assistant_msg["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in decision.tool_calls
            ]
            working_messages.append(assistant_msg)
            for call, result in zip(decision.tool_calls, tool_results):
                tool_content = result.get("content", "")
                if isinstance(tool_content, dict):
                    tool_content = json.dumps(tool_content, ensure_ascii=False)
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": str(tool_content)[:4000],
                })
            working_messages.append({
                "role": "user",
                "content": "Use the tool results above to continue. If they are sufficient, reply with a plain-text final answer for the user. Only call new tools if you still need different information. Do not repeat the same tool calls.",
            })
        else:
            assistant_payload = {"tool_calls": trace.tool_calls, "text": decision.text}
            working_messages.append({"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False)})
            result_summaries = []
            for r in tool_results:
                name = r.get("name", "unknown")
                content = r.get("content", "")
                is_error = r.get("is_error", False)
                tag = "ERROR" if is_error else "OK"
                result_summaries.append(f"[{name}] {tag}: {content[:2000]}")
            working_messages.append({
                "role": "user",
                "content": "Tool results:\n" + "\n---\n".join(result_summaries),
            })

    # 超过最大迭代次数
    if best_text:
        yield self._clean_final_answer(best_text.strip())
    else:
        yield "Stopped after reaching the maximum iteration limit."
```

### 步骤 2：删除不再需要的 `_stream_final_answer` 辅助方法

`_stream_final_answer` 方法可以删除，因为流式逻辑已直接内联到 `run_stream` 中。

---

## 关键设计决策说明

### 为什么不全程使用流式 API？

OpenAI 的流式 API（`stream=True`）不支持解析 `tool_calls`。工具调用阶段必须拿到完整的 JSON 响应才能解析出工具名和参数，所以只能用非流式。

### 为什么 `should_stream_final` 要检查 working_messages 末尾？

因为工具调用可能需要多轮（搜索机票 → 搜索酒店 → 搜索景点），每轮都需要完整的 `complete_with_tools` 返回。只有当工具结果已经追加到消息列表、且模型被提示"如果结果足够就给出最终答案"时，才应该切换到流式。

### 为什么 FINAL_ANSWER 分支也要用 stream_complete？

对于不需要工具的简单问答（如闲聊），`decision.decision_type` 直接就是 `FINAL_ANSWER`，此时也应该用流式 API 重新生成，获得逐 token 输出效果。虽然这意味着多了一次 LLM 调用，但用户体验大幅提升。

### 流式失败回退策略

如果 `stream_complete` 抛出异常（网络问题、API 限流等），回退到非流式的 `complete` 方法，确保用户至少能收到完整回复。

---

## 验证方法

1. 启动后端服务，打开前端页面
2. 发送一条需要工具调用的消息（如"帮我规划厦门3日游"）
3. 观察：
   - 工具调用阶段：前端显示"思考中"动画（TypingIndicator）
   - 最终回复阶段：文本逐字出现，末尾有闪烁光标
   - 回复完成后：光标消失，操作按钮出现
4. 发送一条简单问答（如"你好"）：应该直接逐字流式输出
5. 测试停止生成：流式输出过程中点击停止，文本应该立即停止增长
