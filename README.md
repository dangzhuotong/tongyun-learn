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

接口文档：
- `http://127.0.0.1:8031/v1/docs`

## 环境变量说明

环境变量前缀为 `LEARN_`（KIE API Key 为 `KIE_API_KEY`），完整配置项见 `.env.example`：

- `LEARN_DATABASE_URL`: 数据库连接串（支持 SQLite / MySQL 8.0）
- `LEARN_ROOT_PATH`: FastAPI 反向代理根路径，默认为 `/learn/api`
- `LEARN_CORS_ORIGINS`: 允许跨域来源列表（逗号分隔）
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

