# CIS Cross-Asset Signal Scope Contract

> 本文档是 P0-QNT-001 的契约定义，也是后续新增 signal/data source 时必须遵守的准入规范。
> System invariant：**INV-001 — A BTC-specific exact signal cannot directly change a non-BTC strategy direction.**

## 1. 动机

MarketContextBuilder 此前对所有 instrument 注入 `btc_derivatives` 依赖，策略前端对任意 detail 请求 BTC 衍生品 dashboard，且 ModuleSignal 的 `asset_lens` 默认 `btc_perp`，Direction Resolution 不校验信号与目标资产的关系。由此存在污染路径：

```
BTC derivatives → non-BTC MarketContext → derivatives directional signal
              → DirectionResolution → ETH / HYPE / BNB / OKB strategy
```

## 2. Asset Scope 枚举

每个可能影响 Strategy Direction 的数据源/signal 必须显式声明：

| 字段 | 含义 |
|---|---|
| `instrument_id` | 信号实际观测的标的 |
| `asset_scope` | `exact` / `proxy` / `global` / `unknown` |
| `asset_lens` | 信号所属资产透镜；**禁止再设默认值** |

| scope | 语义 | 方向资格 |
|---|---|---|
| `exact` | 只属于对应资产（如 BTC derivatives 之于 btc-usdt-perp） | 仅当 `signal.instrument_id == target_instrument_id` 时可贡献方向 |
| `proxy` | 可作宏观/代理观察（如 BTC derivatives 之于 ETH） | `directional_weight = 0`，除非存在显式 `CrossAssetProxyPolicy` 且配置允许 |
| `global` | 真正的全市场宏观条件 | 按 global policy 单独准入 |
| `unknown` | 未声明作用域 | **fail closed**：directional eligibility = false |

禁止 fail open。默认值缺失 = `unknown` = 无方向资格。

## 3. Direction Resolution 门禁

```text
resolve(target_instrument_id=..., signals=..., ...)
  for signal in signals:
      if signal.asset_scope == exact and signal.instrument_id != target:
          reject directional contribution        # INV-001
      if signal.asset_scope == proxy:
          directional_weight = 0                 # 除非显式 CrossAssetProxyPolicy
      if signal.asset_scope == unknown:
          reject directional contribution        # fail closed
```

门禁在进入 weighted direction calculation 之前执行；被拒信号可保留为诊断展示，但不得进入方向分数、confirm/veto、entry/stop/target/leverage/position cap 的任何修改。

## 4. 本轮 BTC derivatives 政策（临时安全政策）

本轮不建设 ETH/BNB/HYPE/OKB derivatives service。最小可靠修复：

| 目标资产 | BTC derivatives 资格 |
|---|---|
| BTC（btc-usdt-perp） | `exact` directional evidence——照常参与方向、confirm/veto |
| ETH / HYPE / BNB / OKB | `proxy` market context——最多展示为环境观察，**不得** LONG/SHORT/confirm/veto/修改 entry/stop/target/leverage/position cap/贡献方向分 |

非 BTC 不允许把 BTC derivatives 伪装成本资产 derivatives。未来若需代理传导，必须先建立并验证 `CrossAssetProxyPolicy`。

## 5. Key Level Isolation

`call wall`、`put wall`、`max pain`、BTC spot、BTC option levels 是**资产绝对价格**。禁止应用到非 BTC instrument 的 entry / stop / target / support / resistance / trigger。跨资产传播价位属于明确错误，无 proxy 豁免。

## 6. MarketContextBuilder 注入规则

- BTC：`dependencies.btc_derivatives = {scope: exact, directional_eligible: true}`。
- 非 BTC（本轮采用方案 A）：`dependencies.btc_derivatives = {scope: proxy, directional_eligible: false}`——保留环境观察，剥除方向资格。

## 7. 前端语义

- BTC detail：照常展示「BTC 衍生品」证据。
- 非 BTC detail 若仍展示，必须标注「BTC 市场代理上下文」并附「仅供市场环境参考，不参与本资产方向判定」；禁止呈现为「该资产衍生品」。

## 8. 验证要求（回归测试设计）

不得只检查字段。对 ETH/BNB/HYPE/OKB 分别执行：

1. Scenario 1：BTC derivatives = strongly bullish → 记录 strategy 结果 A；
2. Scenario 2：BTC derivatives = strongly bearish → 记录 strategy 结果 B；
3. 断言 direction / entry / stop / target / readiness / position cap / leverage advice **保持不变**（除非字段被显式定义为 proxy contextual diagnostic）。

Positive control：BTC 自身必须仍能响应 BTC derivatives 变化——不许为隔离把 BTC 功能一起杀掉。
