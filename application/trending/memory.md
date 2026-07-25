# application/trending/ — 模块记忆

## 职责定位
历史热搜抓取的兼容包装层：保留旧函数签名，实际逻辑已委托给 `application/news/hotspot_service.py` 的 `HotspotService`。

## 关键文件
- `manager.py`：保留百度/头条/微博/知乎抓取函数与 `_classify` 主题分类；`refresh_pool` / `get_trending_travel` / `get_trending_news` 为薄包装，委托默认 `HotspotService`。
- `__init__.py`：包占位。

## 业务边界要点
- 公共 API 始终只读缓存；`refresh` 参数已废弃，刷新由后台定时器负责。
- 保留旧签名仅为兼容 `api/server.py` 与 `api/v1/news.py` 的 import；新代码请直接使用 `application/news` 的服务。
