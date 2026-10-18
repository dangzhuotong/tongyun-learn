# 测试覆盖说明文档

本文档记录 `tongyun-learn` 服务的测试体系架构、纯逻辑模块单测覆盖以及全量功能测试现状。

---

## 1. 测试体系设计原则

1. **零外部网络依赖**：所有涉及 AI 调用（KIE API）的测试均采用 `httpx.MockTransport` 模拟 HTTP 响应，不消耗实际模型额度，不依赖外网网络连通性。
2. **纯逻辑模块与数据库解耦**：对于文本规范化、时间时区转换、FSRS 算法调度、入参规范序列化、证据规则判定等纯逻辑模块，单测完全在内存中执行，无需启动或连接数据库，可在毫秒级完成执行。
3. **确定性与抗抖动**：
   - FSRS 卡片调度器在单测与服务层中均显式关闭随机扰动（`enable_fuzzing=False`），确保相同输入产生确定性的间隔与复习安排。
   - 所有时间计算统一基于 naive UTC，对外输出使用标准 ISO-8601 本地时区格式。
4. **状态隔离与幂等验证**：集成测试在每次执行前后自动清理测试表数据，并提供对重复操作、重复导入、软作废恢复的幂等性检验。

---

## 2. 模块测试覆盖矩阵

| 模块分类 | 源文件路径 | 测试文件 | 测试性质 | 覆盖要点说明 |
|---|---|---|---|---|
| **纯逻辑模块** | `services/cardkeys.py` | `tests/test_cardkeys.py` | 单元测试（无DB） | 单词正面规范化（Unicode NFKC、大小写折叠、全半角转换、多余空白合并）、SHA-256 哈希稳定性与碰撞规避 |
| **纯逻辑模块** | `timeutil.py` | `tests/test_timeutil.py` | 单元测试（无DB） | 服务时区配置、naive UTC 时间戳生成、本地时间转 UTC、本地 ISO 格式化、跨天日切界计算（`day_bounds_utc`） |
| **纯逻辑模块** | `services/srs.py` | `tests/test_srs.py` | 单元测试（无DB） | py-fsrs 卡片对象双向转换（`to_fsrs`）、初次学习调度、复习状态转移、Again 评级 lapses 递增逻辑、记忆可提取率计算与时间衰减 |
| **纯逻辑模块** | `services/tutor.py` | `tests/test_tutor_logic.py`<br>`tests/test_p3a_feedback.py` | 单元测试（无DB） | 自测（selftest ≥0.8）、表达（express ≥0.75）达标判定规则 `judge_passed`；表达分比例转换 FSRS 评级 `express_to_rating`；非法分值边界校验 |
| **纯逻辑模块** | `services/insights.py` | `tests/test_insights_logic.py`<br>`tests/test_insights.py` | 单元测试（无DB） | 回顾天数参数解析 `parse_days`（字符串分割、去重、排序、1~365 范围限制、最多 10 个数字限制及非法输入拒绝） |
| **纯逻辑模块** | `ai/service.py`<br>`ai/prompts.py` | `tests/test_ai_logic.py` | 单元测试（无DB） | 助记/语法/错词卷/词书的输入规范化序列化（`canonical_input`）、缓存键生成（`cache_key`）、Prompt 组装（`build_messages`）、修正提示词构造（`repair_message`） |
| **纯逻辑模块** | `errors.py` | `tests/test_errors.py` | 单元测试（无DB） | `ApiError` 状态码、错误代码、详情字段封装与 `to_dict()` 标准响应格式 |
| **纯逻辑模块** | `services/state.py`<br>`services/importer.py` | `tests/test_helpers_logic.py` | 单元测试（无DB） | 词汇点标签判定（`is_vocab`）、进阶证据诉求判定（`needed_evidence`）、卡片稳固状态判定（`_stable`）、过期证据筛选（`stale_evidence`）、卡组命名规范（`deck_name`） |
| **AI 基础能力** | `ai/kie.py` | `tests/test_kie.py` | 单元测试 / Mock | Markdown 代码块与裸 JSON 文本提取解析（`parse_json_text`）、API 异常日志脱敏（API Key 擦除） |
| **AI 校验规则** | `ai/schemas.py` | `tests/test_ai_quiz.py`<br>`tests/test_ai_generate_deck.py` | 校验逻辑测试 | 错词卷题型规则（choice 选项数、答案闭环、cloze 答案泄漏防范）、场景词书单词长度与字母检查 |
| **鉴权与权限** | `auth.py` | `tests/test_auth.py` | 端点测试 | Bearer Token 缺失、格式错误、签名比对、Web 与 阿学 角色权限隔离（如写接口 403 拦截） |
| **限流与配额** | `limits.py` | `tests/test_limits.py` | 逻辑与集成测试 | 进程内滑动令牌桶每分钟限流（HTTP 429 带 Retry-After）、每日 AI 配额按 Token 累加与日切重置、缓存命中不扣配额 |
| **数据模型与迁移** | `models.py`<br>`migrations/` | `tests/test_models.py` | 数据库测试 | 21 张核心业务表完整性、CHECK 约束（证据所属关系校验）、Alembic 迁移双向升级降级周期 |
| **阿学数据迁移** | `migrate_axue.py` | `tests/test_migrate_axue.py` | 迁移逻辑与幂等测试 | 康奈尔笔记文本结构解析（`parse_card`、`parse_feynman`、`parse_express`）、旧课次与卡点映射、重复迁移无副作用验证 |
| **健康检查** | `routers/health.py` | `tests/test_health.py` | 路由集成测试 | `/v1/health`、`/healthz` 存活探针、数据库连接故障降级（503）、全局 404 格式化 |
| **AI 助学接口** | `routers/ai.py` | `tests/test_ai_explain.py`<br>`tests/test_ai_quiz.py`<br>`tests/test_ai_generate_deck.py` | 路由集成测试 | 单词助记与长难句拆解（P2）、错词复习卷（P4）、场景词书生成入库（P4）、缓存命中、模型格式异常重试与降级模型兜底 |
| **卡点管理** | `routers/blockers.py` | `tests/test_blockers.py` | 路由集成测试 | 卡点录入、状态更新（open/resolved/dropped）、知识点未解决卡点数联动统计、列表过滤与排序 |
| **学习洞察** | `routers/insights.py` | `tests/test_insights.py` | 路由集成测试 | 薄弱点排行（`GET /v1/weak`）、间隔复习回顾（`GET /v1/recall`）、每周学习总结（`GET /v1/summary/week`）、人工状态覆盖与撤销防抖（`PATCH /v1/points/{id}/state`） |
| **软作废与恢复** | `routers/voiding.py` | `tests/test_voiding.py` | 路由集成测试 | 课次作废及证据级联作废、证据单独作废及关联复习连带处理、FSRS 复习链路时间序列重放、课次与复习列表过滤 |
| **学习核心** | `routers/learn.py` | `tests/test_p3a_feedback.py` | 路由集成测试 | 知识地图导入审计（`POST /v1/maps/import`）、开局可学点计算、无复习数据时的指标 null 呈现、30天保持率过滤新卡初次学习 |
| **云芽英语手敲** | `routers/en_learn.py`<br>`services/en_progress.py`<br>`services/en_coach.py` | `tests/test_en_typing.py` | 纯逻辑 + 路由集成 | 判分与错误形态、毕业门槛、生活词 20% 上限、今日队列、敲击入库与 FSRS、无密钥规则教练、DeepSeek 假响应入库 |

---

## 3. 测试运行方式

### 运行纯逻辑单元测试（极速，不依赖数据库）

```bash
pytest -q tests/test_cardkeys.py tests/test_timeutil.py tests/test_srs.py tests/test_tutor_logic.py tests/test_insights_logic.py tests/test_ai_logic.py tests/test_errors.py tests/test_helpers_logic.py
```

### 运行全量测试套件（含路由集成与数据库操作）

```bash
pytest -q
```
