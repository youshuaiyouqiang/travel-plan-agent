# domain/user/profile/ — 模块记忆

## 职责定位
用户画像子域：根据交互记录维护用户偏好标签、意图历史与关注领域。

## 关键文件
- `schema.py`：`UserProfile` 数据类（tags、interaction_count、last_intent、preferred_categories、custom_attributes）。
- `manager.py`：`ProfileManager`——画像读写（300s 缓存 TTL）、更新标签/意图/关注领域、构建画像上下文文本（注入 Agent prompt）。
- `__init__.py`：包占位。

## 业务边界要点
- `preferred_categories` 最多保留最近 10 个。
- `interaction_count == 0` 时画像上下文返回空（新用户不注入空画像）。
- 情感识别已从产品删除，画像不含情绪维度（禁恢复清单）。
