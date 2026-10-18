# tongyun-words · AI 开发规则

AI 代理在动任何代码前，必须先完整读一遍本文件。

## 项目概况

- **用途**：基于上游 [TypeWords](https://github.com/zyronon/TypeWords) 的个人自用 fork（GPL-3.0）。对外站点名是「橦云学习」（学习中枢，入口部署在 `/words/`）。背单词、练习、教练是站内模块。另有 AI 讲解、AI 错词复习卷、学习看板。
- **技术栈**：Nuxt 4 + Vue 3 + TypeScript；状态用 Pinia，样式用 UnoCSS + Sass，i18n 用 @nuxtjs/i18n，测试用 Vitest。
- **包管理**：pnpm（见 `pnpm-lock.yaml`、`pnpm-workspace.yaml`）。
- **关键目录**：
  - `app/`：Nuxt 应用主体；学习中枢在 `app/tongyun/`，页面在 `app/pages/`，通用逻辑在 `app/core/`。
  - `public/`：词库（`dicts/`、`list/`）、图片、音效等静态资源。
  - `docs/`：贡献指南、各语言 README、`tongyun-learn-integration.md` 联调文档。
  - `i18n/`：多语言词条（源文件 `i18n.xlsx`）。
  - `scripts/`：构建与部署脚本。
- **部署**：静态生成后部署在子路径 `/words/`；线上与学习服务同域（`/words/` 与 `/learn/api/`）。
- **外部依赖**：AI 讲解、AI 复习卷、学习看板调用 tongyun-learn 学习服务（独立仓库），地址与令牌只存浏览器 localStorage。
- **改动标记**：fork 对上游的改动在代码里带 `tongyun:` 注释，方便日后合并上游。

## 构建和测试

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 安装依赖 | `pnpm install` | 项目根目录执行 |
| 本地开发 | `pnpm dev` | `nuxt dev`，README 称默认 `http://localhost:5567` |
| 构建产物 | `pnpm build` | `nuxt build` |
| 静态生成 | `pnpm generate` | 已内置 `NUXT_APP_BASE_URL=/words/` |
| 预览产物 | `pnpm preview` | `nuxt preview` |
| 单元测试 | `pnpm test` | `vitest run`，匹配 `**/*.test.ts` |
| 生成 i18n | `pnpm i18n:write` | `gulp i18nWrite` |

联调 tongyun-learn 学习服务时，在 **tongyun-learn 仓库** 内执行（见 `docs/tongyun-learn-integration.md`）：

| 场景 | 命令 |
| --- | --- |
| 安装依赖 | `uv sync` |
| 迁移数据库 | `uv run alembic upgrade head` |
| 启动服务 | `uv run uvicorn tongyun_learn.main:app --host 127.0.0.1 --port 8031` |
| 跑测试 | `python -m pytest -q` |

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
