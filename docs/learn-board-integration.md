# 学习看板接口联调与排查说明

TypeWords 前端学习看板（只读页面，位于 `app/pages/learn-board.vue`）依赖 `tongyun-learn` 服务的 6 个只读接口。本服务所有学习接口均位于 `/v1` 路由下，请求时需在 Header 中携带 Bearer 令牌（`Authorization: Bearer $LEARN_TOKEN`）。

---

## 1. 看板依赖的 6 个接口及使用字段

前端类型定义对应 `app/tongyun/learn-board-api.ts`。

| 接口 | 方法 | 前端对应类型 | 看板核心消费字段 | 用途说明 |
|---|---|---|---|---|
| `/v1/subjects` | GET | `Subject[]` | `id`<br>`title`<br>`points_by_state`<br>`goal`（可选） | 学科列表卡片、掌握率计算（各状态点数求和与百分比）以及知识地图学科选择器 |
| `/v1/subjects/{id}/map` | GET | `SubjectMap` | `subject.id`, `subject.title`<br>`stages[].id`, `title`, `ord`, `passed`<br>`stages[].points[].id`, `title`, `ord`<br>`stages[].points[].prereqs[].id`, `kind`<br>`stages[].points[].stats.state` | 知识地图全貌：各阶段（Stage）及阶段内知识点（Point）、节点状态标签颜色与依赖前置关系 |
| `/v1/next?limit=5` | GET | `NextResp` | `new_point_quota.global_left`<br>`new_point_quota.by_subject_left`<br>`recheck[].point_id`, `title`<br>`next[].point_id`, `title`, `state`, `reason`, `opens_today`, `stage_title` | 「今天学什么」区块：全局与各学科剩余新开名额、待复查知识点、推荐学习知识点列表 |
| `/v1/review/due?limit=5` | GET | `ReviewDueResp` | `counts.due_total`<br>`review[].card_id`, `front`<br>`new[].card_id`, `front` | 「待复习」区块：到期复习卡片总数、到期复习卡片正面预览、新卡正面预览 |
| `/v1/progress?subject=` | GET | `ProgressResp` | `retention_30d` | 各学科卡片上的「30天保持率」百分比（保留 1 位小数，无复习数据时返回 null 并显示为 `—`） |
| `/v1/blockers?status=open` | GET | `Blocker[]` | `id`<br>`title`<br>`status`<br>`point_title`（可选）<br>`detail`（可选）<br>`created_at`（可选） | 「卡在哪」区块：当前所有处于 open 状态的卡点列表，展示标题、所属知识点、详细描述和创建日期 |

---

## 2. 使用 curl 快速自查

本地调试可使用以下命令自查各接口连通性与返回格式（将 `$LEARN_TOKEN` 替换为实际环境变量或配置的 Web 客户端令牌，默认端口 `8031`）：

```bash
BASE_URL="http://127.0.0.1:8031/v1"

# 1. 检查学科列表
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/subjects"

# 2. 检查单学科知识地图（以技术英语 tech-english 和 Java java-fde 为例）
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/subjects/tech-english/map"
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/subjects/java-fde/map"

# 3. 检查今日推荐点与名额
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/next?limit=5"

# 4. 检查到期复习队列与卡片数
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/review/due?limit=5"

# 5. 检查学科 30 天记忆保持率
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/progress?subject=tech-english"
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/progress?subject=java-fde"

# 6. 检查 open 状态卡点
curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/blockers?status=open"
```

> **注意**：如果不带 `Authorization` 请求头或令牌错误，所有接口均会返回 HTTP 401（`unauthorized`）。

---

## 3. 常见问题排查（FAQ）

### Q1: 看板只显示一个科目（例如「光有英语」或「光有 Java」）？
- **原因**：看板根据 `GET /v1/subjects` 返回的列表动态渲染卡片。若只展示一个学科，说明服务端数据库中仅导入了单份知识地图 YAML。
- **排查与解决**：
  1. 执行 `curl -s -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/subjects"`，观察返回数组是否仅包含 1 项。
  2. 使用命令行工具一次性导入所需科目的地图 YAML（如英语 + Java）：
     ```bash
     uv run python -m tongyun_learn.cli import-maps --commit maps/english.yaml maps/java-fde.yaml
     ```
  3. 再次请求 `GET /v1/subjects`，确认 `tech-english` 与 `java-fde` 均已在数据库中生效。

### Q2: 卡点区块为空（显示「目前没有卡点」或「卡点记录即将接入」）？
- **原因**：
  1. 服务还是 P3b 之前的版本，没有 `/v1/blockers` 路由，接口返回 404（看板在 404 时显示「卡点记录即将接入」）；或者 P3b 已部署但旧卡点没从阿学迁过来（`migrate_axue` 只预演、没加 `--commit`）。
  2. 数据库中当前确实没有处于 `open` 状态的卡点（已被解决 `resolved`、废弃 `dropped`，或者尚未通过 `POST /v1/blockers` 录入）。
- **排查与解决**：
  1. 执行 `curl -i -H "Authorization: Bearer $LEARN_TOKEN" "$BASE_URL/blockers?status=open"` 检查 HTTP 状态码：
     - 若返回 `404 Not Found`：服务版本太旧，需部署含 P3b（`9ade315` 及以后）的版本并执行 `alembic upgrade head`（部署归运维）。
     - 若返回 `500`：多半是迁移没跑到最新，查 `alembic current`。
     - 若返回 `200 OK` 且内容为 `[]`：接口正常但暂无 open 卡点；旧卡点在阿学那边的，确认 `migrate_axue` 已带 `--commit` 跑过。
  2. 若需录入新卡点，由阿学（或管理员）使用阿学令牌发起请求：
     ```bash
     curl -s -X POST -H "Authorization: Bearer $AXUE_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"title":"测试卡点","point_id":"jf.equals-hashcode","detail":"具体疑惑"}' \
       "$BASE_URL/blockers"
     ```
  3. 录入后再次查询 `GET /v1/blockers?status=open`，即可看到刚录入的卡点；卡点通过 `PATCH /v1/blockers/{id}` 置为 `resolved` 后会自动从 open 列表中消失。
