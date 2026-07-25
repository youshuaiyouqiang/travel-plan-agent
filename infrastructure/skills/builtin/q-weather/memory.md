# infrastructure/skills/builtin/q-weather/ — 模块记忆

## 职责定位
和风天气 Skill：城市/地点天气查询，服务旅行 Agent 的行程天气信息。

## 结构
- `SKILL.md`：frontmatter 声明 `requires.env: WEATHER_API_KEY`。
- `scripts/`：`qweather_tool.py` 实现脚本。

## 业务边界要点
- 需 `WEATHER_API_KEY` 环境变量。
- 天气信息在行程草稿生成后冻结，只在用户点击"更新信息"时重新查询（旅行业务边界）。
