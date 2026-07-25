# infrastructure/skills/builtin/ — 模块记忆

## 职责定位
内置 Skill 集合目录，每个子目录一个 Skill（含 SKILL.md 元数据 + agents/openai.yaml 接口 + 可选 scripts/ 实现）。

## 子目录
- `amap-maps/`：高德地图（POI/路线/地理编码），需 `AMAP_WEBSERVICE_KEY`。
- `fliggy-travel/`：飞猪旅行（机票/酒店查询），基于 flyai-cli 无需 Key（增强需 `FLYAI_API_KEY`）。
- `q-weather/`：和风天气查询，需 `WEATHER_API_KEY`。
- `zhangxuefeng-skill-main/`：张雪峰视角知识 Skill（纯知识/视角，无外部 API）。
- `scripts/`：空目录（占位）。

## 业务边界要点
- 新增 Skill：建子目录 + SKILL.md（frontmatter 声明 name/description/requires.env）+ agents/openai.yaml，`FileSkillProvider` 自动发现。
- 各 Skill 的 Key 走环境变量，不写入 SKILL.md 或代码。
