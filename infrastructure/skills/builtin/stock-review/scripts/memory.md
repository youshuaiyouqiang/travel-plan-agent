# scripts 目录说明

本目录存放 skill 的工具实现代码（function call handler）。

**当前状态**：占位。工具实现将在后续开发文档中定义。

预期工具（与 openai.yaml 配合）：
- `get_market_snapshot` — 大盘指数 + 情绪指标聚合
- `get_emotion_indicators` — 情绪周期 6 维指标
- `get_strong_repair_leaders` — 上次强修复日领涨板块延续性
- `get_sector_rotation` — 板块轮动
- `get_watchlist` — 观察池
- `get_stock_daily` — 个股日线
- `get_signal_stocks` — 当日抗跌/新周期信号股

实现原则：
- 只读 SQLite 缓存，不直接调用 akshare。
- 通过端口（protocol）注入数据源，便于测试。
- 失败时返回空，由调用方标注"数据缺失"。
