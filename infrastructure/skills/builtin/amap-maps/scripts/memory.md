# infrastructure/skills/builtin/amap-maps/scripts/ — 模块记忆

## 职责定位
高德地图 Skill 的实现脚本目录。

## 文件
- `amap_tool.py`：调用高德 Web 服务 API（POI/路线/地理编码）的实现。

## 业务边界要点
- Key 从环境变量 `AMAP_WEBSERVICE_KEY` 读取，不硬编码。
- 外部调用失败应返回结构化错误，不抛裸异常给 LLM。
