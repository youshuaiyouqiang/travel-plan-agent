# infrastructure/skills/builtin/fliggy-travel/scripts/ — 模块记忆

## 职责定位
飞猪旅行 Skill 的实现脚本目录。

## 文件
- `flyai_quick.py`：flyai-cli 快速查询封装（机票/酒店信息）。
- `setup.py`：环境安装/初始化辅助。

## 业务边界要点
- 基础查询无需 Key；`FLYAI_API_KEY` 为可选增强，走环境变量。
- 只查询不交易。
