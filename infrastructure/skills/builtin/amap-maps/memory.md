# infrastructure/skills/builtin/amap-maps/ — 模块记忆

## 职责定位
高德地图 Skill：POI 搜索、路线规划、地理编码等能力，服务旅行 Agent 的地点/路线查询。

## 结构
- `SKILL.md`：frontmatter 声明名称/描述/`requires.env: AMAP_WEBSERVICE_KEY`。
- `agents/openai.yaml`：工具接口与 i18n 定义。
- `scripts/`：`amap_tool.py` 等实际调用高德 Web 服务 API 的实现脚本。

## 业务边界要点
- 需要 `AMAP_WEBSERVICE_KEY` 环境变量；未配置时 SkillCenter 显示未就绪。
- 只供旅行规划查询（地点/天气/路线边界），不涉及预订/支付。
