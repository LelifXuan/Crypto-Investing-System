# SECRET ROTATION REQUIRED

> P0-SEC-001 产物。只记录凭证名称与轮换要求，**不记录任何凭证值**。
> 背景：2026-08-31 及更早的 PRIVATE 便携 ZIP（`dist/CIS-UI2-*-PRIVATE-*.zip`，共 2 个归档）
> 按当时设计包含真实 `source/.env`，并产生过带密钥的临时解压目录。凡进入过这些归档/副本的
> 凭证都应视为已离开本机信任边界。

## 轮换总原则

- 第三方 provider 的密钥轮换需要登录对应控制台操作：**MANUAL ROTATION REQUIRED**，在完成前不得声称已轮换。
- 本机自管 secret（JWT / bootstrap 密码）可通过修改本地 `source/.env` 完成：ROTATION REQUIRED。
- 自 2026-09-30 起新构建的便携包不含任何 `.env`（构建器 fail-closed secret gate），不再产生新的分发暴露。

## 凭证清单（键名来自 `source/.env`，值未记录）

### 分发暴露的历史密钥 —— MANUAL ROTATION REQUIRED

| Credential name | 用途 | Rotation required | Reason |
|---|---|---|---|
| `FRED_API_KEY` | 宏观 FRED | **MANUAL — NOT YET PERFORMED** | 进入过 2026-08-31 PRIVATE ZIP |
| `BLS_API_KEY` | 宏观 BLS | **MANUAL — NOT YET PERFORMED** | 同上 |
| `BEA_API_KEY` | 宏观 BEA | **MANUAL — NOT YET PERFORMED** | 同上 |
| `TIINGO_API_KEY` | 行情 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `TWELVEDATA_API_KEY` | 行情 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `ALPHA_VANTAGE_API_KEY` | 行情 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `COINMARKETCAP_API_KEY` | 行情 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `OPENEXCHANGERATES_APP_ID` | 汇率 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `NASDAQ_DATA_LINK_API_KEY` | 宏观 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `GLASSNODE_API_KEY` | 链上 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `TUSHARE_TOKEN` | A股数据 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `ZHITUAPI_TOKEN` | 中文数据源 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `AGUSHUJU_API_KEY` | A股数据 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `GATEIO_API_KEY` / `GATEIO_API_SECRET` | 交易所行情 | **MANUAL — NOT YET PERFORMED** | 同上 |
| `TENCENT_TMT_SECRET_ID` / `TENCENT_TMT_SECRET_KEY` | 腾讯翻译 | **MANUAL — NOT YET PERFORMED** | 同上 |

### 本机自管 secret —— ROTATION REQUIRED（本地 .env 更新即可）

| Credential name | 用途 | Rotation required | Reason |
|---|---|---|---|
| `JWT_SECRET_KEY` | 本地会话签发 | **REQUIRED — NOT YET PERFORMED** | 运行中的 `source/.env` 仍在使用与已提交 `.env.example` 相同的示例默认值（该默认值随历史包分发过）；可伪造本地 token |
| `BOOTSTRAP_ADMIN_PASSWORD` | 首启管理员 | **REQUIRED — NOT YET PERFORMED** | 同上：运行值等于已提交的示例默认值 |
| `.env.example` 中的示例默认值 | — | **已处置（2026-09-30）** | `.env.example` 两个示例值已改为显式 `CHANGE_ME`，门禁不再放行真实形态默认值 |

### 非凭证但进入过归档的配置

| Key | 说明 | Action |
|---|---|---|
| `HTTPS_PROXY` | 代理地址 | 视为内部网络信息，随包流转可接受；如代理带内嵌凭证则按上表处理 |

## 已完成的缓解（2026-09-30）

1. `build_private_portable.py` 移除 `.env` 携带与强制要求；构建前后两次 fail-closed secret scan，命中即删产物并中止构建。
2. `scripts/verify_portable_package.py` 交付校验：档案级 secret scan + 结构检查 + 可选解压核验（临时目录 try/verify/finally，cleanup 失败显式上报）。
3. README「历史敏感包」段落改为如实描述：旧包含密钥、新包不含。

## 待人工动作

- [ ] 登录各 provider 控制台轮换上列 15 组密钥（MANUAL）。
- [ ] 更新本地 `source/.env` 的 `JWT_SECRET_KEY` 与 `BOOTSTRAP_ADMIN_PASSWORD`。
- [ ] 处理已流出的历史 ZIP：确认接收人清单，召回或销毁不再需要的副本（含临时解压目录）。
