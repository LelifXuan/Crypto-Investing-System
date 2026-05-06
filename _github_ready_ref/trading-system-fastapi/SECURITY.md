# Security Policy

## Supported Versions

这是一个仍在快速演进的工程骨架。通常只承诺维护默认分支上的最新版本。

## Reporting a Vulnerability

请不要在公开 issue 中披露安全漏洞细节。

建议流程：
1. 使用 GitHub 的 private vulnerability reporting（如果仓库已启用）
2. 或联系仓库维护者的私下联系方式
3. 在获得确认前，不公开 PoC、密钥、利用细节或受影响资产信息

## Scope Notes

以下内容尤其敏感：
- API Key / Secret 管理
- 本地 secrets 加密存储
- 认证鉴权恢复为多用户模式时的访问控制
- 事件总线与后台 worker 的重放与重算逻辑
- 接入真实交易执行前后的权限边界

## Hardening Recommendations

如果你将本项目用于更高风险场景，至少增加：
- 独立密钥管理
- 审计日志
- 速率限制
- 更严格的认证与 RBAC
- 生产级消息队列与缓存
