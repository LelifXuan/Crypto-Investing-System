# Trading System FastAPI

一个面向**单用户本地模式**的交易系统管理工程骨架，基于 **FastAPI + PostgreSQL + SQLAlchemy + Alembic**，并优先集成 **Gate API** 作为实时价格与技术指标数据源。

> 当前定位：**研究 / 个人管理 / 回测分析 / 本地观察**。
> 
> 默认**不是实盘执行系统**，也**不是托管式多用户 SaaS**。

## 核心能力

- 仓位管理（fills、position snapshots、重建逻辑）
- 盈利计算（realized / unrealized / funding / cash / fx）
- 交易复盘（notes、tags、策略上下文）
- 技术指标（SMA / EMA / RSI / MACD / BBANDS，可扩展）
- 市场价格（REST + WebSocket）
- 市场事件信息（公告 / RSS / 强平事件聚合）
- Fill 幂等中间件（`Idempotency-Key`）
- 事件总线驱动的异步重算（Outbox + Worker）
- Gate API Key/Secret 本地加密存储（文件加密，不入库）
- 单用户本地模式（默认不开登录，仅允许 localhost）

## 当前运行模式

默认配置更适合**只有你自己在本机使用**的场景：

- `SINGLE_USER_MODE=true`
- 服务默认监听 `127.0.0.1`
- 中间件拒绝非 loopback 请求
- 不要求注册 / 登录 / JWT
- API 凭证走本地 secrets 文件加密

如果你之后要：
- 从别的设备访问
- 部署到云服务器
- 开放局域网访问
- 接入真实下单执行

建议重新启用认证鉴权，并加上更严格的密钥管理、审计和限流。

## 项目结构

```text
.
├── .github/                 # CI、Issue 模板、PR 模板
├── alembic/                 # 数据库迁移
├── api/                     # OpenAPI 草案
├── app/
│   ├── api/                 # FastAPI 路由层
│   ├── cache/               # 本地缓存
│   ├── core/                # 配置、安全、secrets
│   ├── db/                  # ORM models
│   ├── events/              # 事件总线/处理器
│   ├── integrations/        # Gate / RSS / 外部集成
│   ├── middleware/          # localhost 限制、幂等
│   ├── repositories/        # 数据访问层
│   ├── schemas/             # Pydantic 模型
│   ├── services/            # 领域服务
│   └── workers/             # 后台 worker
├── db/                      # SQL schema
├── docs/                    # 架构和发布文档
├── prompts/                 # 给 Codex 的任务提示
├── scripts/                 # 打包与发布辅助脚本
└── tests/                   # 单元测试
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- PostgreSQL 15+
- Docker（可选，用于本地数据库）

### 2. 本地启动

```bash
cp .env.example .env
pip install -e .[dev]
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. 建议的初始化顺序

1. `POST /api/v1/bootstrap/seed`
2. `GET /api/v1/auth/me`
3. `PUT /api/v1/local-secrets/gate`
4. `GET /api/v1/market-prices/cache/marks/latest?instrument_id=btc-usdt-perp`
5. `POST /api/v1/indicators/policies`
6. `POST /api/v1/market-events/sync`

## Gate API Key 本地加密存储

写入示例：

```json
{
  "api_key": "your-gate-api-key",
  "api_secret": "your-gate-api-secret",
  "passphrase": null,
  "label": "main-account"
}
```

接口：
- `GET /api/v1/local-secrets/gate`
- `PUT /api/v1/local-secrets/gate`
- `DELETE /api/v1/local-secrets/gate`

说明：
- 明文不会进入数据库
- secrets 写入 `LOCAL_SECRETS_DIR` 下的加密文件
- 对称密钥保存在本机单独 key 文件
- `.gitignore` 已排除 `.local_secrets/`

## 开源发布建议

这个仓库已经按 GitHub 开源发布做了基础整理：

- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `.github/ISSUE_TEMPLATE/`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/workflows/ci.yml`
- `docs/open-source-release.md`
- `scripts/create_release_zip.py`
- `.gitattributes`（配合 `git archive` 导出干净 zip）

发布到 GitHub 前，建议你检查：

- 是否替换了 `LICENSE`（默认 MIT，可按需要改为 Apache-2.0 / GPL）
- 是否修改 `SECURITY.md` 中的安全联系方式
- 是否确认没有提交 `.env`、数据库快照、`.local_secrets/`
- 是否确认 README 中的定位符合你最终要公开的范围

## 常用命令

```bash
make install
make db-up
make migrate
make test
make lint
make check
make release-zip
```

## 生成适合 GitHub 发布的 zip

```bash
python scripts/create_release_zip.py
```

默认输出到：

```text
dist/trading-system-fastapi-github.zip
```

如果你使用 Git 仓库，也可以：

```bash
git archive --format=zip --output dist/source.zip HEAD
```

本仓库提供 `.gitattributes`，可帮助归档时自动排除缓存、测试缓存、本地 secrets、编辑器目录等不应随 zip 分发的内容。

## 测试

```bash
pytest -q
```

## 许可

本仓库默认附带 `MIT License`。

## 风险声明

本项目用于学习、研究和个人系统搭建参考，不构成投资建议，也不保证适合实盘交易。使用任何市场数据、策略逻辑或接口接入前，请自行评估风险，并根据你的司法辖区、交易所条款和安全要求完成合规与风控设置。
