"""SQLite 仓储实现子包（P2.1+）.

按业务聚合组织仓储，每个文件实现 domain 层定义的端口。
所有 SQL 和 JSON 序列化集中于此，domain/application 只消费端口。
"""

from __future__ import annotations
