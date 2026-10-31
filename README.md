<h1 align="center">橦云学习</h1>

<p align="center">
  <b>背单词、练习与 AI 教练，一个面向个人学习的开源站点</b>
</p>

## 简介

橦云学习是一个背单词与练习工具，前端基于 [Nuxt 4](https://nuxt.com/) + Vue 3 + TypeScript，学习服务最初是一个 FastAPI 项目，现归档在 [`legacy/`](legacy/README.md)。

站内模块：

- **背单词 / 练习**：跟打、默写、自测、看词拼写，按记忆曲线智能混学，配合教练页手敲巩固。
- **AI 讲解 / AI 记忆法**：单词记忆法与文章句子讲解，调用同域学习服务 `/learn/api/v1/ai/explain`。
- **AI 错词复习卷**（`/ai-quiz`）：从错词本选词生成 cloze / 选择 / 英译中，本地判分。
- **学习看板**（`/learn-board`）：手机优先的只读页面，显示今日任务、待复习、卡点与各科统计。

静态站默认挂在子路径 `/learn/`，与学习服务同域（`/learn/` 与 `/learn/api/`）。

前端基于 [TypeWords](https://github.com/zyronon/TypeWords)（GPL-3.0）二次开发，对上游的改动在代码里带 `tongyun:` 标记，方便日后合并上游。

## 环境要求

- **Node.js >= 24**（版本见 [`.nvmrc`](.nvmrc)，可用 `nvm use` 切换）
- **pnpm**（版本锁定在 `package.json` 的 `packageManager`，与 `pnpm-lock.yaml` 一致）

## 快速开始

```bash
pnpm install --frozen-lockfile   # 安装依赖
pnpm dev                         # 本地开发，默认 http://localhost:5567/learn/
pnpm test                        # 单元测试（Vitest）
pnpm run audit                   # 依赖安全审计（高危告警为 0）
pnpm build                       # 构建服务端产物
pnpm generate                    # 静态全量生成（产物在 .output/public）
```

静态生成用 `pnpm generate`，默认 base `/learn/`，产物在 `.output/public`。要换子路径就在命令前加 `NUXT_APP_BASE_URL`，例如 `NUXT_APP_BASE_URL=/preview/ pnpm generate`。

站内「背单词」页面路由是 `/words`（部署后是 `/learn/words`），这是页面路由，不是站点 base。

## 环境变量

根目录的环境变量见 [`.env.example`](.env.example)，复制为 `.env` 后按需填写：

```bash
cp .env.example .env
```

- `NUXT_APP_BASE_URL`：静态站子路径，默认 `/learn/`。
- `WORDS_DATABASE_URL`、`WORDS_SESSION_SECRET`、`WORDS_STATS_TOKEN`、`WORDS_BOSS_USER`、`WORDS_BOSS_PASS_HASH`：Nitro / 背单词接口使用，只在服务端进程读取。
- `BAIDU_TRANSLATE_APPID`、`BAIDU_TRANSLATE_KEY`：Nitro 百度翻译服务端代理使用，密钥只在服务端读取，严禁注入前端构建产物。

密钥与令牌只存本地或环境文件，不要写进仓库。

## 对接与架构说明

- **tongyun-words**：原独立的背单词代码库已整体归档，其背单词/做练习核心、做题记录与前端历史提交已全部合并进本仓库根目录（Nuxt 4 + Nitro）。做题数据（`words_attempts`、`words_card_state`）通过 Nitro 服务端接口保存到 MySQL（由 `WORDS_DATABASE_URL` 配置）。
- **学习导师「阿学」**：阿学是负责出题判分、课次推进、证据达标校验（mastery_evidence）的学习导师 Agent，对接本仓库 `legacy/` 目录下的 FastAPI 学习服务（提供 `/learn/api/v1/...`）。阿学持有专用的 Bearer Token（由 `LEARN_TOKEN_AXUE_SHA256` 鉴权），拥有写课与证据验收权限；Web 客户端仅具有只读及做题提交权限。
- **百度翻译服务端代理**：文章页生词与长难句翻译不再直接走前端调用第三方 API，统一由服务端 Nitro 路由 `/learn/api/translate` 代理转发。由服务端保管 `BAIDU_TRANSLATE_APPID` 与 `BAIDU_TRANSLATE_KEY` 环境变量并计算 MD5 签名。密钥完全不打进前端或静态 HTML 产物，未配置时接口优雅降级，前端不报错。

## 目录

| 路径 | 内容 |
| --- | --- |
| 仓库根（`app/`、`public/`、`package.json`） | Nuxt 前端，主应用 |
| `public/dicts/`、`public/list/`、`public/wordlists/` | 词表内容，请勿修改 |
| `legacy/` | 旧 FastAPI 学习服务。命令在该目录执行，说明见 [`legacy/README.md`](legacy/README.md) |
| `docs/` | 前端贡献说明、各语言 README、联调说明 |
| `server/` | Nitro 服务端接口与数据库迁移 |

## 旧后端（legacy/）

`legacy/` 是被替换前的 Python 学习服务，仍在 82 上提供 `/learn/api`（本机 `127.0.0.1:8031`）。部署反代把 `/learn/api/` 转到 `127.0.0.1:8031/`。

```bash
cd legacy
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn tongyun_learn.main:app --host 127.0.0.1 --port 8031 --reload
```

完整命令与测试方式见 [`legacy/AGENTS.md`](legacy/AGENTS.md) 与 [`docs/tongyun-learn-integration.md`](docs/tongyun-learn-integration.md)。

## 贡献

贡献指南见 [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)。提问或反馈请开 Issue，欢迎提交 PR。

## 许可

本项目基于 [TypeWords](https://github.com/zyronon/TypeWords) 二次开发，遵循 [GPL-3.0](LICENSE)。
