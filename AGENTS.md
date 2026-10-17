# tongyun-learn · AI 开发规则

所有 AI 代理在动手前必须先读本文件，遵守其中的构建、测试与代码审查规矩。

## 项目概况

- 定位：tongyun-learn 是给 tongyun-words（TypeWords 分支）和「阿学」用的学习服务后端，负责知识地图、FSRS 卡片复习调度、证据过关判定与 AI 讲解代理，并包含云芽英语手敲（今日队列、敲词/敲句、DeepSeek 教练）。
- 技术栈：Python 3.10+、FastAPI、Uvicorn、SQLAlchemy 2.0、Alembic、Pydantic Settings、py-fsrs；数据库支持 SQLite 与 MySQL 8.0（pymysql）。
- 依赖与工具：使用 uv 管理依赖（`pyproject.toml` / `uv.lock`），开发依赖为 pytest 与 ruff（line-length 120，py310）。
- 入口与目录：应用入口 `tongyun_learn/main.py`；路由在 `tongyun_learn/routers/`；业务逻辑在 `tongyun_learn/services/`；AI 适配在 `tongyun_learn/ai/`；数据与词表在 `tongyun_learn/data/`。
- 数据与迁移：`maps/` 存放知识地图 YAML（english/ java-fde 等），Alembic 迁移在 `migrations/versions/`。
- 测试：`tests/` 为单元与集成测试，`docs/` 存放测试体系与看板联调说明，`deploy/` 存放生产部署文件。
- 配置：环境变量前缀 `LEARN_`，完整项见 `.env.example`（如 `LEARN_DATABASE_URL`、`LEARN_DOCS_ENABLED`、`LEARN_ROOT_PATH` 等）。密钥与令牌只存哈希或环境文件，不入库、不入仓库。

## 构建和测试

| 用途 | 命令 |
|---|---|
| 安装/同步依赖 | `uv sync` |
| 拷贝环境配置 | `cp .env.example .env` |
| 迁移到最新 | `uv run alembic upgrade head` |
| 回滚到初始 | `uv run alembic downgrade base` |
| 启动开发服务 | `uv run uvicorn tongyun_learn.main:app --host 127.0.0.1 --port 8031 --reload` |
| 代码规范检查 | `uv run ruff check .` |
| 纯逻辑单测（快） | `uv run pytest -q tests/test_cardkeys.py tests/test_timeutil.py tests/test_srs.py tests/test_tutor_logic.py tests/test_insights_logic.py tests/test_ai_logic.py tests/test_errors.py tests/test_helpers_logic.py` |
| 全量测试 | `uv run pytest -q` |
| 种子英语课表 | `uv run python -m tongyun_learn.cli seed-english` |
| 导入知识地图（预演） | `uv run python -m tongyun_learn.cli import-maps maps/english.yaml maps/java-fde.yaml` |
| 导入知识地图（真导入） | `uv run python -m tongyun_learn.cli import-maps --commit maps/english.yaml maps/java-fde.yaml` |

CI（`.github/workflows/ci.yml`）会跑 `uv run ruff check .`、`uv run pytest -q`，并在 MySQL 8.0 上验证迁移（`alembic upgrade head` / `downgrade base` / `alembic check`）与 MySQL 下的全量测试。

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
