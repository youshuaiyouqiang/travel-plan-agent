# infrastructure/skills/builtin/fliggy-travel/ — 模块记忆

## 职责定位
飞猪旅行 Skill：机票/酒店等旅行信息查询，基于 flyai-cli，服务旅行 Agent 的出行信息检索。

## 结构
- `SKILL.md`：frontmatter 声明（基础功能无需 Key，增强功能需 `FLYAI_API_KEY`）。
- `agents/openai.yaml`：工具接口与 i18n 定义。
- `scripts/`：`flyai_quick.py`、`setup.py` 等实现脚本。

## 业务边界要点
- 仅作规划信息查询与外部搜索入口，不形成预订/支付/订单流程（业务禁恢复清单）。
