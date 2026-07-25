# frontend/public/ — 模块记忆

## 职责定位
Vite 静态资源目录：不经打包、按原路径提供。

## 文件
- `favicon.svg`：站点图标，被 `index.html` 通过 `/favicon.svg` 引用。

## 业务边界要点
- 无业务逻辑；新增静态文件（robots.txt 等）放此处。
