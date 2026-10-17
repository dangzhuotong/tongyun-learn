<h1 align=center>
  <img src="https://github.com/user-attachments/assets/9d626e0f-0601-4640-8981-ad66d8ac4853" alt="TypeWords" style="width: 500px;"/>
</h1>

<p align="center">
  <a href="/README.md">English</a> |
  <a href="/docs/README.es.md">Español</a> |
  <a href="/docs/README.de.md">Deutsch</a> |
  <a href="/docs/README.fr.md">Français</a> |
  <a href="/docs/README.pt.md">Português</a> |
  <a href="/docs/README.ru.md">Русский</a> |
  <a href="/docs/README.uk.md">Українська</a> |
  <a href="/docs/README.ja.md">日本語</a> |
  <a href="/docs/README.ko.md">한국인</a> |
  <a href="/docs/README.th.md">ไทย</a> |
  <a href="/docs/README.vi.md">Tiếng Việt</a> |
  <a href="/docs/README.id.md">Bahasa Indonesia</a> |
  <a href="/docs/README.zh-TW.md">繁體中文</a> |
  <a href="/docs/README.zh-CN.md">简体中文</a> 
</p>

<p align="center">
  <b>Learn English, one keystroke at a time; smarter memorization, more efficient learning - an open-source word and article practice tool</b>
</p>

<!-- tongyun: fork 说明 -->
## 关于这个 fork（tongyun-words）

基于 [TypeWords](https://github.com/zyronon/TypeWords) 的个人自用 fork，同样以 GPL-3.0 开源。在上游功能之外加了这些（改动处代码里都带 `tongyun:` 标记，方便以后合并上游）：

- **橦云学习**（学习中枢门面。站点入口 `/`，部署后仍是 `/words/`）：今日、练习、教练、设置是站内模块，背单词在练习里。先整词手敲再整句手敲，空格继续。今天学几项、要不要敲句都听 tongyun-learn 的 `GET /v1/today`；敲完 `POST /v1/type`（`card_id`、`phase`、`typed`、`duration_ms`）；教练页 `GET/POST /v1/coach`。令牌仍在设置里，只存本机。旧地址 `/typewords` 会进练习。视觉见 [DESIGN.md](DESIGN.md)。
- **子路径部署**：`pnpm generate` 使用 `NUXT_APP_BASE_URL=/words/`。
- **智能混学**：跨词书按记忆曲线复习，再随机补新词，不分章节。
- **AI 记忆法 / AI 讲解**：单词记忆法和文章句子讲解，调同域的学习服务 `/learn/api/v1/ai/explain`。学习服务地址和令牌在「设置 → 通用设置」顶部填写，只存在本浏览器 localStorage。
- **AI 错词复习卷**（`/ai-quiz`，部署后是 `/words/ai-quiz`）：从错词本选词，调 `/learn/api/v1/ai/quiz` 生成 cloze / 选择 / 英译中，本地判分。复用同一份学习服务地址和令牌。
- **学习看板**（`/learn-board`，部署后是 `/words/learn-board`）：手机优先的只读页面，按顺序显示今天学什么（待复查在前，新点标出会不会占今天的新开名额）、待复习数和前几张卡的正面、卡点、各科统计（掌握数、各状态数、30 天保持率）、按阶段折叠的知识地图（点开一个点能看到硬前置和软前置）。
  - 复用设置里的同一份学习服务地址和令牌。没填令牌时只提示去设置，不发任何请求。
  - 只调学习服务的 GET 接口：`/subjects`、`/subjects/{id}/map`、`/next`、`/review/due`、`/progress`、`/blockers`。每块单独加载、单独报错：令牌不对提示去设置改，连不上提示「连不上学习服务」；连到没有 `/blockers` 的旧版服务（404）时显示「卡点记录即将接入」。
  - 页面是 `ssr:false` 的纯客户端页面，静态产物里没有任何学习数据。
- 本机联调、探活命令和常见错误见 [docs/tongyun-learn-integration.md](docs/tongyun-learn-integration.md)。
- 默认关闭了原作者的第三方统计脚本（开关在 `app/tongyun/config.ts`）。

## Project Introduction

<https://www.bilibili.com/video/BV1QwYv6eEAS>

## Online Access

<https://typewords.cc>

<img width="1920" height="1440" alt="practice words" src="/public/imgs/words.png" />
<img width="1920" height="1440" alt="practice articles" src="/public/imgs/articles.png" />

## Features

### Word Practice

- Practice modes: Follow-along / Dictation / Self-test / Spelling from memory
- Smart mode: Automatically calculates learning words based on memory curves, deepening memory through dictation
- Free mode: No restrictions, plan your own learning
- Provides phonetics, pronunciation (American/British), example sentences, phrases, synonyms, root words, etymology, error statistics, and more

### Article Memorization

- Built-in classic textbooks; you can also add or import articles with one-click translation and bilingual comparison
- Follow-along + dictation dual modes, sentence-by-sentence input with automatic pronunciation for more efficient memorization
- Supports listening while writing from memory to reinforce learning

### Favorites, Wrong Words, Mastered

- Words typed incorrectly while learning are automatically added to your wrong word book for later review
- Actively add words to mastered to automatically skip them in future sessions
- Add words to favorites for consolidation and review

### Highly Customizable

- Rich keyboard sound effects
- Customizable shortcuts
- Highly configurable settings

### Clean and Efficient

- Clean design, modern UI, ad-free
- Refreshing interface, simple operation
- No forced subscription to any platform

### Vocabulary Library

Built-in commonly used vocabulary including CET-4, CET-6, GMAT, GRE, IELTS, SAT, TOEFL, Graduate English, TEM-4, TEM-8, and more (official website only).
Designed to meet most users' vocabulary learning needs. Community contributions of additional vocabulary are welcome.

## Running the Project

#### Note: This project can run standalone with data saved locally. Manual backup is required when switching devices; this does not affect normal usage.

This project is built with `Nuxt` and requires a Node.js environment.

1. Install NodeJS, refer to the [official documentation](https://nodejs.org/en/download)
2. The project is large. It's recommended to use `git clone --depth 1 https://github.com/zyronon/TypeWords.git` to clone only the latest commit. GitHub's Download ZIP feature will not work properly.
3. In the project root directory, open a terminal and run `pnpm install` to download dependencies.
4. Run `pnpm run dev` to start the project. The default address is [`http://localhost:5567`](http://localhost:5567)
5. Open [`http://localhost:5567`](http://localhost:5567) in your browser to access the project.
6. Run `pnpm run generate` to build the project files.

## Features and Suggestions

The project is currently in early development, with new features being added continuously. If you have any suggestions or feature requests, feel free to open an `Issue`.
If you like the design philosophy of this software, please submit a `PR`. Thank you for your support!

## Contributing Guide

[Contributing Guidelines](/docs/CONTRIBUTING.md)

If you're interested in this project, we welcome your contributions and will provide as much help as possible.

Before contributing, please communicate with the developers to avoid code conflicts.

Thank you again for your contributions!


## ❤️ Support TypeWords
If TypeWords has been helpful to you, feel free to sponsor the project to support server operation and future development.  
Of course, sponsorship is not required for use—sharing the project, submitting feedback, or contributing code are also highly valuable forms of support.

<img width="300" height="390" alt="practice words" src="/public/imgs/zhifubao.png" />
<img width="300" height="390" alt="practice words" src="/public/imgs/weixin.png" />

