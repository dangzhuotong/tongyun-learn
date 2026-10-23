# 词表（阿学定制 v1.0）

分级：L1 AI 核心术语 / L2 X/社区用语 / L3 技术文档词汇 / L4 NGSL 基础词 / L5 推文/README/PR 写作 / L6 面试表达（可选）

- `en-ngsl.json`：L4，2234 条。选词派生自 NGSL 1.2（Browne, C., Culligan, B. & Phillips, J.，https://www.newgeneralservicelist.com/），CC BY-SA 4.0（https://creativecommons.org/licenses/by-sa/4.0/）。已筛选并加注。文件头 `license_note` 为完整出处；本文件单独存放，按 CC BY-SA 4.0 共享。
- `en-tongyun.json`：L1 252 / L2 254 / L3 397 / L5 139 / L6 96，共 1138 条。自编，不含 NGSL 派生内容。
- 音标取自 [ECDICT](https://github.com/skywind3000/ECDICT)（MIT License），已规范化为英式 IPA。`phonetic_note` 标注「未经词典核对」的为自写或推导。
- 语体 `register` 只取 `technical` | `neutral` | `informal` | `slang` | `formal`（文件顶层 `register_values`）。
- 字段：word / phonetic（多读法用逗号分隔）/ phonetic_note / meaning / register / example / example_zh / tag / level(1–6) / point_id（对齐 tech-english 28 个知识点；L2 与 L5 发推用 en.x-community）/ source。
- 知识点 `point_id`：对齐技术英语（`tech-english`，定义见 `legacy/maps/english.yaml`）28 个合法知识点：
  - s1 词汇与句子：`en.vocab-general`、`en.vocab-java`、`en.vocab-ai`、`en.abbreviations`、`en.long-sentence`、`en.spec-words`
  - s2 读技术文档：`en.doc-navigation`、`en.read-readme`、`en.read-javadoc`、`en.read-changelog`、`en.read-errors`、`en.read-ai-docs`
  - s3 写作：`en.commit-message`、`en.write-issue`、`en.write-readme`、`en.write-pr-review`、`en.ask-for-help`
  - s4 听力：`en.listen-numbers`、`en.listen-signposts`、`en.listen-shadowing`、`en.listen-talk-summary`、`en.listen-tutorial-follow`
  - s5 面试与表达：`en.self-intro`、`en.explain-concept`、`en.project-pitch-en`、`en.behavioral-star`、`en.clarify-and-confirm`、`en.handle-unknown`
  - 注释例外：L2（X/社区用语）与 L5 发推（tweet）使用 `en.x-community`。
