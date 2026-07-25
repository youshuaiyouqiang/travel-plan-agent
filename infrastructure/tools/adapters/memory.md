# infrastructure/tools/adapters/ — 模块记忆

## 职责定位
外部服务/CLI 的工具适配层：把高德、和风天气、飞猪、HTTP 等外部能力包装为统一 `ToolSpec` 注册进工具总线。

## 关键文件
- `amap.py`：高德地图服务适配（POI/路线/地理编码）。
- `qweather.py`：和风天气适配。
- `fliggy.py`：飞猪旅行适配。
- `drive_cost.py`：自驾成本估算工具。
- `http.py`：HTTP 通用请求工具。
- `interaction.py`：用户交互类工具（提问/确认）。
- `shared.py`：全局共享基础工具（不绑定 skill/MCP 的 Layer 3 能力）。

## 业务边界要点
- 通过 `bind_tool` 注册到 `ToolSpec`；工具的可用性受 policy 白名单与限流约束。
- 外部 Key 全部走环境变量；调用失败返回结构化错误。
