# Contributing

感谢你关注这个项目。

## 贡献范围

欢迎的贡献包括：
- bug 修复
- 文档改进
- 单元测试补充
- 指标、数据源、事件源扩展
- 性能优化与代码重构

当前**不建议**直接提交以下内容，除非先开 issue 讨论：
- 大规模目录重构
- 改变默认单用户本地模式的行为
- 未说明风险边界的实盘执行能力
- 会引入闭源依赖或强绑定商业服务的改动

## 开始之前

1. 先阅读 `README.md`、`SPEC.md`、`docs/architecture.md`
2. 对较大改动先开 issue 说明目标和影响范围
3. 保持提交尽量小而清晰

## 本地开发

```bash
cp .env.example .env
pip install -e .[dev]
docker compose up -d postgres
alembic upgrade head
pytest -q
ruff check .
```

## 代码风格

- Python 3.11+
- 尽量补类型标注
- 新功能尽量补测试
- 不把敏感信息写进代码、测试夹具或示例配置
- 尽量保持 router / service / repository 分层清晰

## Pull Request 建议

请在 PR 中说明：
- 改了什么
- 为什么要改
- 影响了哪些模块
- 如何验证
- 是否涉及数据结构、迁移、接口变化

## 提交前检查

至少确保：

```bash
ruff check .
pytest -q
python -m compileall app tests
```

## 安全相关问题

安全漏洞不要直接公开提 issue。请阅读 `SECURITY.md`。
