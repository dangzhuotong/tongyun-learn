# 橦云学习 · AI 开发规则

AI 代理在动任何代码前，必须先完整读一遍本文件。旧 Python 服务的细则在 `legacy/AGENTS.md`，命令以 `legacy/` 为工作目录。

## 项目概况

- **用途**：本仓库是「橦云学习」的单一代码库。[tongyun-words](https://github.com/dangzhuotong/tongyun-words) 已归档，前端和它的提交历史都在这里。站点名是「橦云学习」。背单词、练习、教练是站内模块。另有 AI 讲解、AI 错词复习卷、学习看板。
- **前端**：Nuxt 4 + Vue 3 + TypeScript，在仓库根目录。状态用 Pinia，样式用 UnoCSS + Sass，i18n 用 @nuxtjs/i18n，测试用 Vitest。包管理是 pnpm（`pnpm-lock.yaml`）。静态站默认 base 是 `/learn/`，用 `NUXT_APP_BASE_URL` 覆盖。站内页面路由 `/words` 是背单词，不是站点 base。
- **旧后端**：`legacy/` 是被替换前的 FastAPI 学习服务，仍在 82 上提供 `/learn/api`（本机 `127.0.0.1:8031`）。技术栈与命令见 `legacy/AGENTS.md`。
- **词表**：`public/dicts/`、`public/list/`、`public/wordlists/` 是词表内容，不要改。
- **关键目录**：
  - `app/`：Nuxt 应用主体；学习中枢在 `app/tongyun/`，页面在 `app/pages/`，通用逻辑在 `app/core/`。
  - `public/`：词库、图片、音效等静态资源。
  - `legacy/`：旧学习服务（`tongyun_learn/`、`tests/`、`maps/`、`migrations/`、`deploy/`）。
  - `docs/`：贡献指南、各语言 README、`tongyun-learn-integration.md` 联调文档。
  - `i18n/`：多语言词条（源文件 `i18n.xlsx`）。
  - `scripts/`：构建与部署脚本。
- **部署**：`npm run generate` 的静态站挂在 `/learn/`，与学习服务同域（`/learn/` 与 `/learn/api/`）。
- **学习服务**：AI 讲解、AI 复习卷、学习看板、今日队列调用 `legacy/` 里的服务，地址与令牌只存浏览器 localStorage。
- **改动标记**：fork 对上游 TypeWords 的改动在代码里带 `tongyun:` 注释，方便日后合并上游。前端基于 [TypeWords](https://github.com/zyronon/TypeWords)（GPL-3.0）。

## 构建和测试

在仓库根目录：

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 安装依赖 | `pnpm install` | 使用 `pnpm-lock.yaml` |
| 本地开发 | `pnpm dev` | `nuxt dev`，默认 `http://localhost:5567/learn/` |
| 构建产物 | `pnpm build` | `nuxt build` |
| 静态生成 | `npm run generate` | `nuxt generate`。默认 base `/learn/`；`NUXT_APP_BASE_URL` 可覆盖 |
| 预览产物 | `pnpm preview` | `nuxt preview` |
| 单元测试 | `pnpm test` | `vitest run`，匹配 `**/*.test.ts` |
| 生成 i18n | `pnpm i18n:write` | `gulp i18nWrite` |

旧学习服务在 `legacy/` 内执行（见 `legacy/AGENTS.md` 与 `docs/tongyun-learn-integration.md`）：

| 场景 | 命令 |
| --- | --- |
| 安装依赖 | `uv sync` |
| 迁移数据库 | `uv run alembic upgrade head` |
| 启动服务 | `uv run uvicorn tongyun_learn.main:app --host 127.0.0.1 --port 8031` |
| 跑测试 | `uv run pytest -q` |

CI（`.github/workflows/ci.yml`）的 Python 任务工作目录是 `legacy/`：`uv run ruff check .`、`uv run pytest -q`，并在 MySQL 8.0 上验证迁移。

## 代码审查规矩

1. **本地测试进 PR**：改代码必须在本地跑相关测试，把测试命令和输出贴进 PR 描述（或附件）。没跑过别声称通过。
2. **提 PR 前自查 diff**：提交前自己过一遍 diff，重点看正确性、兼容（旧接口/旧数据）、权限、生命周期（启停、清理、泄漏）。
3. **已知坑沉淀**：同类问题第二次出现，就写进本文件「已知坑」一节（没有就新建），避免反复踩。
4. **AI 改稿轮次上限**：AI 修改来回审超过 3 轮还没过，停下重想方案并上报（阿码/阿审），不要硬改硬怼。
5. **风险分级合入**：
   - **低风险**：文档、测试的小改动，CI 绿可直接合。
   - **功能改动**：要阿审审过再合。
   - **高风险（必须阿橦本人批）**：计费、密钥相关、CI/发布流程（`.github/workflows`、updater、签名）的改动。

不要把密钥、Token、密码写进本文件或仓库任何位置。
