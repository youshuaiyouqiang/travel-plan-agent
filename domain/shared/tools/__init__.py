"""纯内存工具模型、注册表、策略与执行器。

P4.2 引入：``ToolSpec`` / ``Tool`` / ``ToolRegistry`` / ``ToolPolicy`` /
``ToolExecutor`` / ``ToolCatalog`` 均为纯内存逻辑，不依赖外部 I/O。
从 ``infrastructure/tools/`` 迁移到 domain，消除 domain → infrastructure 违规。
具体 HTTP / 地图 / 天气 / 飞猪等适配器仍留在 ``infrastructure/tools/adapters/``。
"""
