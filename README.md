# tongyun-learn

tongyun-learn 是给 tongyun-words（TypeWords 分支）和 阿学 用的学习服务后端，负责知识地图、FSRS 卡片复习调度、证据过关判定与 AI 讲解代理。

## 本地运行

依赖 Python 3.10+。推荐使用虚拟环境：

```bash
# 安装依赖（uv）
uv sync

# 拷贝环境配置
cp .env.example .env

# 启动开发服务器
uv run alembic upgrade head
uv run uvicorn tongyun_learn.main:app --host 127.0.0.1 --port 8031 --reload
```

访问健康检查接口：
- `http://127.0.0.1:8031/v1/health`
- `http://127.0.0.1:8031/healthz`

接口文档（默认关闭，生产不开；本机调试设 `LEARN_DOCS_ENABLED=true` 后可看）：
- `http://127.0.0.1:8031/v1/docs`、`/v1/openapi.json`

AI 接口目前已实现 `POST /v1/ai/explain`（P2）与 `POST /v1/ai/quiz`（P4 错词复习卷）；`/ai/generate-deck` 属于 P4，尚未实现。

## 环境变量说明

环境变量前缀为 `LEARN_`（KIE API Key 为 `KIE_API_KEY`），完整配置项见 `.env.example`：

- `LEARN_DATABASE_URL`: 数据库连接串（支持 SQLite / MySQL 8.0）
- `LEARN_ROOT_PATH`: FastAPI 反向代理根路径，默认为 `/learn/api`
- `LEARN_CORS_ORIGINS`: 允许跨域来源列表（逗号分隔）；TypeWords 和看板与服务同域（82 上 `/learn/api` 反代），留空即可
- `LEARN_DOCS_ENABLED`: 是否开放 `/v1/docs` 和 `/v1/openapi.json`，默认 `false`
- `LEARN_TOKEN_WEB_SHA256`: Web 客户端 Bearer Token 的 SHA256 哈希值
- `LEARN_TOKEN_AXUE_SHA256`: 阿学 Bearer Token 的 SHA256 哈希值
- `LEARN_RATE_WEB_PER_MIN`: Web 客户端每分钟限流阈值（默认 60）
- `LEARN_RATE_AXUE_PER_MIN`: 阿学每分钟限流阈值（默认 120）
- `LEARN_AI_DAILY_WEB`: Web 端每日 AI 调用上限（默认 200）
- `LEARN_AI_DAILY_AXUE`: 阿学每日 AI 调用上限（默认 500）
- `LEARN_AI_MODEL`: 主 AI 模型（默认 `gemini-3-8-flash-openai`）
- `LEARN_AI_FALLBACK_MODEL`: 降级 AI 模型（默认 `deepseek-v4-1-flash`）
- `LEARN_AI_TIMEOUT_S`: AI 请求超时秒数（默认 30.0）
- `LEARN_KIE_BASE_URL`: KIE AI API 基础地址（默认 `https://api.kie.ai`）
- `KIE_API_KEY`: KIE AI API 鉴权密钥（注意不加 LEARN_ 前缀，日志不泄露）
- `LEARN_TZ`: 服务时区（默认 `Asia/Shanghai`）

## 数据库迁移

使用 Alembic 进行数据库版本管理：

```bash
# 执行迁移升级至最新版本
alembic upgrade head

# 回滚至初始版本
alembic downgrade base
```

## 测试与代码检查

```bash
# 代码规范与静态检查
ruff check .

# 运行全量单元测试与集成测试
pytest -q
```

## 生产部署

生产部署使用 systemd 单进程管理，详细 systemd unit 文件与安全注意事项请参考 [deploy/tongyun-learn.service](deploy/tongyun-learn.service)。
注意：由于服务内置进程内令牌桶限流，请务必保持 `--workers 1` 单 worker 模式。

## 学习接口（P3a）

规格见定稿 `2026-10-07-tongyun-learn-schema.md` §2/§4。全部在 `/v1` 下，web 令牌只读 + `POST /review(/batch)`（看不到动手卡），其余写接口仅 axue。

| 接口 | 说明 |
|---|---|
| `POST /maps/import?dry_run=true\|false` | 导入知识地图 YAML（`{files:[...]}`），校验 → 增量 upsert → diff；有 error 不写库；幂等 |
| `GET /subjects`、`GET /subjects/{id}/map`、`GET /points/{id}` | 学科 / 整棵地图（带 PointStats、阶段 passed）/ 单点详情 |
| `POST /points/{id}/cards`、`PATCH /cards/{id}` | 批量建卡（按 front 去重）/ 改卡停卡（示例卡改后 created_by→axue） |
| `GET /decks`、`POST /decks`、`POST /decks/{id}/cards` | 卡组 |
| `GET /review/due` | 每日队列：到期复习 + 新卡（配额、积压阻断、新开点每学科 2 / 全局 3） |
| `POST /review`、`POST /review/batch` | 复习（py-fsrs，`client_review_id` 幂等，乱序只记日志；支持 en_word 形态） |
| `GET /progress` | 各状态点数、今日到期、30 天保持率、近 7 天、阶段过关 |
| `POST /sessions`、`POST /evidence` | 记课、记证据（服务端判 passed；带 card_id 同时写一次 FSRS） |
| `GET /next` | 待复查点（全部）+ 推荐学习的点 |
| `POST /v1/ai/quiz` | 错词 AI 复习卷：输入 1–20 个错词生成复习测试卷（完形填空/单选/英译中），去重与规范排序后支持缓存与重试 |

### P3b：卡点、薄弱点、回顾与软作废

都在 `/v1` 下。「任一令牌」指 web 和 axue 都能调；写接口只认 axue。

| 接口 | 谁能调 | 说明 |
|---|---|---|
| `GET /blockers?status=&point=&limit=` | 任一令牌 | 卡点列表（默认 200 条，最多 500） |
| `POST /blockers`、`PATCH /blockers/{id}` | axue | 记卡点 / 改状态（解决、搁置等） |
| `GET /weak?subject=` | 任一令牌 | 薄弱点排行 |
| `GET /recall?days=1,3,7` | 任一令牌 | 按间隔天数回顾当天学过的内容 |
| `GET /summary/week?ago=0` | 任一令牌 | 周小结，`ago` 表示往前第几周 |
| `PATCH /points/{id}/state` | axue | 手动改知识点状态 |
| `GET /sessions?date_from=&date_to=&point=&subject=&include_voided=&limit=` | 任一令牌 | 课时记录，默认不含已作废 |
| `GET /reviews?card=&point=&include_voided=&limit=` | 任一令牌 | 复习记录，默认不含已作废 |
| `POST /sessions\|evidence\|reviews/{id}/void` | axue | 软作废一条课时 / 证据 / 复习，带原因；作废后按剩余记录重算状态 |
| `POST /sessions\|evidence\|reviews/{id}/restore` | axue | 撤销作废 |

AI 接口（`/v1/ai/*`）见下文「AI 讲解接口」和上表的 `POST /v1/ai/quiz`；`/v1/ai/generate-deck` 还没实现。

状态重算（`tongyun_learn/services/state.py`）在每次写入的同一事务里跑，沿硬前置下游连锁，不需要定时任务。

### 种子数据（知识地图）

`maps/` 下是阿学的知识地图副本（源文件在 box 的 `/workspace/learning/knowledge-maps/`）。导入是幂等的，可重复执行：

```bash
uv run python -m tongyun_learn.cli import-maps maps/english.yaml maps/java-fde.yaml            # 预演，打印 diff
uv run python -m tongyun_learn.cli import-maps --commit maps/english.yaml maps/java-fde.yaml   # 真导入
```

### 学习看板联调

看板依赖的 6 个接口契约字段、curl 自查与排查说明见 [docs/learn-board-integration.md](docs/learn-board-integration.md)。

## AI 讲解接口

`POST /v1/ai/explain` 为学习者提供单词记忆法（`word_mnemonic`）与长难句语法拆解（`sentence_grammar`）的 AI 助学接口。

### 鉴权与调用方
- 请求头需携带 `Authorization: Bearer <token>`，通过 SHA256 与服务配置匹配，支持 `web`（TypeWords 客户端）和 `axue`（阿学）。
- 接口经进程内令牌桶限流（`LEARN_RATE_WEB_PER_MIN` / `LEARN_RATE_AXUE_PER_MIN`）。
- 每日调用受限于 AI 日额度（`LEARN_AI_DAILY_WEB` / `LEARN_AI_DAILY_AXUE`，在 `api_usage` 记录），未命中缓存的实际 AI 调用扣除 1 次配额；超限返回 429。

### 缓存机制
- 缓存键为 `sha256(kind|model|prompt_ver|input_canonical)`。
- 命中缓存时直接返回结果（`cached: true`），**不触发实际 KIE AI 调用**，且**不计入当日 AI 调用额度**。

### 请求与响应示例

#### 1. 单词记忆助记 (`word_mnemonic`)

**请求示例**：
```json
POST /learn/api/v1/ai/explain
Content-Type: application/json
Authorization: Bearer <token>

{
  "kind": "word_mnemonic",
  "input": {
    "word": "abandon",
    "context": "放弃，抛弃"
  }
}
```

**响应示例 (200 OK)**：
```json
{
  "kind": "word_mnemonic",
  "model": "gemini-3-8-flash-openai",
  "prompt_ver": "w1",
  "cached": false,
  "content": {
    "word": "abandon",
    "phonetic": "/əˈbændən/",
    "meanings": [
      {"pos": "v.", "cn": "放弃；抛弃"},
      {"pos": "n.", "cn": "放任；放纵"}
    ],
    "examples": [
      {"en": "They had to abandon the burning car.", "zh": "他们不得不弃车离开。"},
      {"en": "He abandoned the software project due to lack of funding.", "zh": "因资金不足，他放弃了该软件项目。"}
    ],
    "roots": [
      {"part": "a-", "type": "prefix", "meaning": "加强语气"},
      {"part": "bandon", "type": "root", "meaning": "控制；命令"}
    ],
    "etymology": "源自古法语 abandoner，原意指脱离控制或任凭摆布。",
    "mnemonic": "一个(a)胖墩(bandon)把作业给“放弃”了",
    "related": [
      {"word": "ban", "cn": "禁止"},
      {"word": "abandoned", "cn": "被遗弃的"}
    ]
  }
}
```

#### 2. 语法句子拆解 (`sentence_grammar`)

**请求示例**：
```json
POST /learn/api/v1/ai/explain
Content-Type: application/json
Authorization: Bearer <token>

{
  "kind": "sentence_grammar",
  "input": {
    "sentence": "The database optimizes queries that execute frequently.",
    "context": "技术英语数据库调优"
  }
}
```

**响应示例 (200 OK)**：
```json
{
  "kind": "sentence_grammar",
  "model": "gemini-3-8-flash-openai",
  "prompt_ver": "s1",
  "cached": false,
  "content": {
    "sentence": "The database optimizes queries that execute frequently.",
    "translation": "数据库会对频繁执行的查询进行优化。",
    "structure": [
      {"text": "The database", "role": "主语", "explain": "句子的核心执行者"},
      {"text": "optimizes", "role": "谓语", "explain": "第三人称单数及物动词"},
      {"text": "queries", "role": "宾语", "explain": "谓语动词的作用对象"},
      {"text": "that execute frequently", "role": "定语从句", "explain": "修饰先行词 queries 的关系从句"}
    ],
    "grammar_points": [
      {"name": "that引导的定语从句", "explain": "that在从句中充当主语，修饰queries"}
    ],
    "key_words": [
      {"word": "optimize", "pos": "v.", "cn": "优化", "note": "常用于性能调优场景"}
    ],
    "difficulty": "medium"
  }
}
```

#### 3. 错词 AI 复习卷 (`POST /v1/ai/quiz`)

**请求示例**：
```json
POST /learn/api/v1/ai/quiz
Content-Type: application/json
Authorization: Bearer <token>

{
  "words": [
    {"word": "abandon", "cn": "放弃"},
    {"word": "ability", "cn": "能力"}
  ]
}
```

**响应示例 (200 OK)**：
```json
{
  "kind": "word_quiz",
  "model": "gemini-3-8-flash-openai",
  "prompt_ver": "q1",
  "cached": false,
  "content": {
    "questions": [
      {
        "type": "cloze",
        "word": "abandon",
        "stem": "The crew had to ___ the sinking ship.",
        "options": [],
        "answer": "abandon",
        "explain": "根据语境，船员不得不弃船，填 abandon。"
      },
      {
        "type": "choice",
        "word": "ability",
        "stem": "He has demonstrated a great ___ to lead the team.",
        "options": ["ability", "abandon", "absence", "abroad"],
        "answer": "ability",
        "explain": "ability 表示能力，符合语境。"
      }
    ]
  }
}
```

### 错误码说明

所有错误均遵循统一错误格式 `{"error": {"code": str, "message": str, "details": any}}`：

| HTTP 状态码 | Error Code | 触发原因 |
|---|---|---|
| 401 | `unauthorized` | 缺少或无效的 Bearer 令牌 |
| 403 | `forbidden` | 令牌权限不足 |
| 422 | `validation_error` | 请求入参不合法（如 word 未包含英文字母或超出长度） |
| 429 | `rate_limited` | 请求过于频繁（超过每分钟令牌桶阈值，携带 `Retry-After`） |
| 429 | `ai_daily_cap` | 今日 AI 次数已用完（携带 `Retry-After` 至次日零点秒数） |
| 502 | `ai_bad_output` | AI 模型输出格式校验失败（经重试仍无法解析） |
| 502 | `ai_unavailable` | AI 服务超时或网络异常，降级均失败 |
| 503 | `ai_not_configured` | 服务端未配置 `KIE_API_KEY` |

