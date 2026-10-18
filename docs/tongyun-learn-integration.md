# 与 tongyun-learn 联调

tongyun-words 的 AI 讲解、AI 错词复习卷、学习看板都调学习服务 tongyun-learn。线上两者同域（`/words/` 和 `/learn/api/`），本机联调按下面来。

## 本机起服务

1. 起 tongyun-learn（在它的仓库里，详见其 README）：

   ```bash
   cp .env.example .env
   # 自己定一个 web 令牌，把它的 sha256 写进 .env：
   #   LEARN_TOKEN_WEB_SHA256=$(printf '%s' "$LEARN_TOKEN" | sha256sum | cut -d' ' -f1)
   # words 和 learn 不同源，本机要放开 CORS：
   #   LEARN_CORS_ORIGINS=http://localhost:3000
   uv run alembic upgrade head
   uv run uvicorn tongyun_learn.main:app --host 127.0.0.1 --port 8031
   ```

   想真调 AI 还要配 `KIE_API_KEY`；不配也能测鉴权和参数校验。

2. 起 words：`pnpm dev`（默认 `http://localhost:3000`）。
3. 打开橦云学习的「设置」（`/settings`）：地址填 `http://127.0.0.1:8031/`（本机没有 `/learn/api` 前缀），令牌填 `$LEARN_TOKEN` 的原文。地址和令牌只存在本浏览器 localStorage。线上反代则地址保持默认 `/learn/api/`。

## 用到的接口

| 页面 | 接口 |
| --- | --- |
| 设置页「测试连接」 | `GET /v1/health`，再用 `POST /v1/ai/explain` 空请求测令牌（422 视为令牌有效） |
| AI 记忆法 / 讲解 | `POST /v1/ai/explain` |
| AI 错词复习卷 `/ai-quiz` | `POST /v1/ai/quiz`（1–20 个错词） |
| 学习看板 `/learn-board` | `GET /v1/subjects`、`/v1/subjects/{id}/map`、`/v1/next`、`/v1/review/due`、`/v1/progress`、`/v1/blockers` |
| 今日 `/`、练习 `/practice` | `GET /v1/today` |
| 练习提交 | `POST /v1/type`，正文只有 `card_id`、`phase`（`A` 或 `B`）、`typed`、`duration_ms`。`card_id` 用今日队列里的那一个 |
| 教练 `/coach` | `GET /v1/coach` 读报告，`POST /v1/coach` 请服务端重算（没有 DeepSeek 时后端按规则排，前端不自己排） |

地址和令牌仍是上面这一份。线上 base 写 `/learn/api/`（反代会去掉这段前缀，请求落到服务根上的 `/v1/...`）；本机直连写 `http://127.0.0.1:8031/`。今天练几项、某一项是敲词还是敲句，只看今日队列。队列字段名有几套常见写法时做薄适配，例如 `items` / `queue` / `cards`、`phase` / `stage`、`cn` / `meaning`、`sentence_zh` / `prompt`。例句在 `payload.sentences` 里时，只有该项明确要敲句才会变成敲句步骤。

```bash
curl -s $BASE/v1/today -H "Authorization: Bearer $LEARN_TOKEN"
curl -s -X POST $BASE/v1/type \
  -H "Authorization: Bearer $LEARN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"card_id":1,"phase":"A","typed":"oppose","duration_ms":1200}'
curl -s $BASE/v1/coach -H "Authorization: Bearer $LEARN_TOKEN"
curl -s -X POST $BASE/v1/coach -H "Authorization: Bearer $LEARN_TOKEN" -H 'Content-Type: application/json' -d '{}'
```

视觉记号见仓库根目录 `DESIGN.md`。

## 探活

```bash
BASE=http://127.0.0.1:8031          # 线上换成 https://<域名>/learn/api
curl -s $BASE/v1/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/v1/ai/quiz      # 期望 401（没带令牌）
curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/v1/ai/quiz \
  -H "Authorization: Bearer $LEARN_TOKEN" -H 'Content-Type: application/json' -d '{}'   # 期望 422（令牌对，参数缺）
curl -s $BASE/v1/subjects -H "Authorization: Bearer $LEARN_TOKEN"     # 期望 200
```

`422` 那条不会调 AI、不扣额度，适合日常探活。

## 常见错误

| 现象 | 原因 | 怎么办 |
| --- | --- | --- |
| 401 / 403 | 令牌不对，或服务端没配对应的 `LEARN_TOKEN_*_SHA256` | 设置页重填令牌；核对 sha256 |
| 422 | 请求参数不对（比如错词为空或超过 20 个） | 看返回的 `error.message` |
| 429 | 每分钟限流或当日 AI 额度用完 | 等一会儿；额度见 `LEARN_AI_DAILY_WEB` |
| 「连不上学习服务」 | 地址错、服务没起、本机跨域没放开 | 先 curl `/v1/health`；本机检查 `LEARN_CORS_ORIGINS` |
| 看板卡点区显示「即将接入」 | 连的是没有 `/v1/blockers` 的旧版服务 | 升级 tongyun-learn |
