# infrastructure/skills/builtin/q-weather/scripts/ — 模块记忆

## 职责定位
和风天气 Skill 的实现脚本目录。

## 文件
- `qweather_tool.py`：调用和风天气 API 的实现。

## 业务边界要点
- Key 从环境变量 `WEATHER_API_KEY` 读取，不硬编码。
