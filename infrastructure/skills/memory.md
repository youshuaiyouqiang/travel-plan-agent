# infrastructure/skills/ — 模块记忆

## 职责定位
Skill 系统：从文件系统加载模块化技能定义（SKILL.md + agents/openai.yaml），供 Agent 绑定使用。

## 关键文件
- `provider.py`：抽象 `SkillProvider` + `FileSkillProvider`——解析 `SKILL.md` 前置元数据（frontmatter）与 `agents/openai.yaml` 接口/i18n 定义。
- `__init__.py`：包占位。

## 子目录
- `builtin/`：内置 Skill 集合（高德地图、飞猪旅行、和风天气、张雪峰视角）。

## 业务边界要点
- 每个 Skill 必须含 `SKILL.md`；按 `requires.env` 判定 `env_configured` 状态（前端 SkillCenter 展示）。
- `academic` 类 Agent 的工具白名单排除 `web_search`（学术边界强制）。
