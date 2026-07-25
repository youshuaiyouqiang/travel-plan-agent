# frontend/src/test/ — 模块记忆

## 职责定位
Vitest 测试环境全局 setup。

## 文件
- `setup.ts`：引入 `@testing-library/jest-dom/vitest`；beforeEach/afterEach 清空 localStorage/sessionStorage/cookie，保证测试隔离。

## 业务边界要点
- 存储清理与"认证 token 不持久化"红线测试配合，防止跨用例污染。
