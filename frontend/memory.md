# frontend/ — 模块记忆

## 职责定位
React 18 + TypeScript strict + Vite 6 前端工程根目录：构建、类型、测试、样式与运行环境配置。

## 关键文件
- `vite.config.ts`：开发服务器 `127.0.0.1`，`/api` 代理到 `http://127.0.0.1:8000`；react 插件 + tsconfig 路径别名。
- `package.json`：React 18.3、react-router-dom 7、zustand 5、leaflet、framer-motion 等；脚本 `dev/build/lint/test`（vitest）、`check`（tsc）。
- `tsconfig.json`：strict 全开（含 noUnusedLocals/noUnusedParameters），别名 `@/* → src/*`。
- `vitest.config.ts`：jsdom 环境，setup 为 `src/test/setup.ts`。
- `tailwind.config.js` / `postcss.config.js`：Tailwind 3 配置（darkMode: class）。
- `eslint.config.js`：ESLint 9 flat config（js + tseslint + react-hooks + react-refresh）。
- `index.html`：HTML 入口，挂载 `/src/main.tsx`。
- `.env`：`VITE_PUBLIC_URL`（分享链接基址）与 `VITE_AMAP_KEY`（高德前端 Key）。

## 业务边界要点
- TypeScript strict 强制：禁止新增 `any`、未使用导入、ESLint 禁用注释。
- 开发期所有 `/api` 请求经 Vite 代理到后端 8000 端口。
- 依赖安装以 `package-lock.json` 为准（`npm ci`）。
