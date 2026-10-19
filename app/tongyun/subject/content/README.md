# 学科题库内容

这里放各学科题库 JSON，结构见 `../types.ts`、解析与校验见 `../parse.ts`。

- `java-v0.1.json`、`ai-v0.1.json`：由 **学习-阿学** 自写的题库（生成脚本 `gen_qb.py`），
  为自有内容，随仓库分发；卡片 id 与内容不要改动，删卡只标 `retired`。
- `fde-v0.1.json` / `web-v0.1.json` / `writing-v0.1.json` / `ip-v0.1.json` / `tools-v0.1.json`：
  五科共 154 张卡，结构与 Java/AI 兼容，走同一套加载器（`../bank.ts` 动态 import），
  已在 `../subjects.json` 登记；卡片 id 与内容不要改动，删卡只标 `retired`。
- `map_point` 缺省或为 `null` 表示「待挂」：照常排课，但 `../map.ts` 的知识地图进度不计。

要点：

- 旧字段保持兼容：`points`、`items` 里新增的 `level` / `unit` / `map_point` / `refs` /
  `options` / `rubric` / `grading` / `retired` 全部可选。
- `choice`：`options` 至少 3 个、互不重复，`answer` 必须在 `options` 里，程序自动判分。
- `oral` / `project`：`grading: "self"`，`rubric` 3–5 条，界面按 会 / 半会 / 不会 三档自评。
- 未知学科会直接抛错，不会静默回落到 Java。
