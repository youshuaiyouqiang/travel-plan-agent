# infrastructure/skills/builtin/amap-maps/agents/ — 模块记忆

## 职责定位
高德地图 Skill 的 Agent 接口定义目录。

## 文件
- `openai.yaml`：OpenAI function calling 格式的工具接口声明与 i18n 文案，由 `FileSkillProvider` 解析。

## 业务边界要点
- 修改工具参数 schema 在此文件；实现逻辑在 `../scripts/`。
