# 橦云学习

橦云学习是一个智能学习中枢与练习系统，包含背单词、手敲练习、AI 记忆法讲解、AI 错词复习卷与个人学习看板等功能模块。前端采用 Nuxt 4、Vue 3 与 TypeScript 构建，以轻量、高效、专注为核心体验。

## 环境要求 (Requirements)

- **Node.js**：`>= 24`（根目录已提供 `.nvmrc`，推荐使用 `nvm use` 切换至 Node 24）
- **包管理器**：`pnpm`（版本请与 `package.json` 中的 `packageManager` 保持一致，推荐 pnpm 10）

## 环境配置 (.env Setup)

项目根目录提供 `.env.example` 作为环境变量配置模板：

```bash
# 复制示例配置文件
cp .env.example .env
```

按需修改 `.env` 中的配置项：
- `NUXT_APP_BASE_URL`：站点部署子路径，默认为 `/learn/`。
- `API_BASE` / `ORIGIN` / `HOST`：前端运行时配置。
- `WORDS_DATABASE_URL`：数据库连接字符串（仅服务端进程读取，切勿暴露给前端）。
- `WORDS_SESSION_SECRET` / `WORDS_STATS_TOKEN` 等服务端认证密钥。

> **安全提示**：切勿将真实密码、Token 或 API Key 提交到代码仓库。

## 常用命令 (Scripts)

在仓库根目录下执行：

### 1. 安装依赖

```bash
pnpm install
```

### 2. 本地开发

```bash
pnpm dev
```

默认开发服务器地址为 `http://localhost:5567/learn/`。

### 3. 运行测试

```bash
pnpm test
```

### 4. 构建产物

```bash
# 生产构建
pnpm build

# 静态站点生成（输出至 .output/public）
npm run generate
```

## 关于旧服务 (Note on legacy/)

仓库中的 `legacy/` 目录保留了被替换前的 FastAPI Python 学习服务：
- 使用 `uv` 管理依赖与环境。
- 在被完全替代前，仍在特定环境下提供 `/learn/api` 接口与知识地图/卡片调度功能。
- 详细的使用说明、接口文档及测试方法参见 [`legacy/README.md`](legacy/README.md) 与 `legacy/AGENTS.md`。

## 许可说明

本项目前端基于开源项目二次开发，遵循 GPL-3.0 协议；所有定制修改均以 `tongyun:` 标注以便追溯。
