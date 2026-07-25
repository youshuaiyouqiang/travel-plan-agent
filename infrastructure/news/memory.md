# infrastructure/news/ — 模块记忆

## 职责定位
新闻来源抓取适配层：将各平台抓取函数包装为统一 fetch 协议，按域名分发到对应 provider。

## 关键文件
- `fetchers.py`：按域名匹配 provider（baidu/toutiao/weibo/zhihu）抓取热点；`_DOMAIN_DISPATCH` 集中登记域名映射。
- `__init__.py`：包入口。

## 业务边界要点
- 抓取失败返回空列表不抛异常（上游保留最后成功缓存）。
- 只返回标题/来源/URL/摘要，**绝不返回新闻全文**。
- 只有 `enabled` 来源会被定时任务抓取（由 application/news 的 HotspotService 控制）。
- 新增来源平台在 `_DOMAIN_DISPATCH` 登记，不散落各处。
