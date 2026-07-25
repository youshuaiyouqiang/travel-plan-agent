# infrastructure/skills/builtin/zhangxuefeng-skill-main/ — 模块记忆

## 职责定位
"张雪峰视角"知识型 Skill：纯知识/观点视角能力，不调用外部 API、无需环境变量。

## 结构
- `SKILL.md`：Skill 元数据与使用说明。
- `examples/`：使用示例。
- `references/`：参考资料；`references/research/` 含 6 个调研文档。

## 业务边界要点
- 纯知识 Skill，无 requires.env，无外部 I/O。
- 输出属于观点/视角类内容，应与事实类回答区分。
