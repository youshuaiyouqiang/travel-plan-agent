---
name: openakita/skills@q-weather
description: "QWeather weather skill for location lookup, current weather, daily forecast, and hourly forecast. Use when the user wants real-time weather, city lookup, or forecast information from the QWeather API."
license: MIT
metadata:
  author: openakita
  version: "1.0.0"
requires:
  env: [WEATHER_API_KEY]
---

# 和风天气

基于 QWeather 的天气查询能力，适合实时天气、地点查询、逐日预报和小时预报。

## 适用场景

- 查询某个城市或地点的实时天气
- 根据地点名、地点 ID 或经纬度查询地点信息
- 获取未来 3/7/10/15/30 天游预报
- 获取未来 24/72/168 小时预报

## 配置

设置环境变量：

```bash
export WEATHER_API_KEY=your_qweather_api_key
```

## 使用方式

优先复用仓库里的天气适配器：

- `src/openakita/integrations/adapters/weather.py`
- `tests/integration/test_api_adapters.py`

QWeather provider 的调用方式：

```python
from openakita.integrations.adapters.weather import create_weather_adapter

adapter = create_weather_adapter("qweather", {"api_key": WEATHER_API_KEY})
await adapter.get_weather("101010100")
await adapter.get_forecast("101010100", days=3)
```

## 处理规则

1. 先识别用户要的是地点查询、实况天气、日预报还是小时预报
2. 尽量使用地点 ID；只有在用户只给出城市名时才先做地点查询
3. 输出时保留温度、天气现象、风力、湿度、降水概率等关键字段
4. 如果缺少 `WEATHER_API_KEY`，先提示配置，再继续查询

