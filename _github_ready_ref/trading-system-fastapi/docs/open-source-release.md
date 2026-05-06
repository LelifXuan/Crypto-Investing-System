# Open Source Release Notes

## 发布前检查

### 1. 安全与隐私

- 确认没有提交 `.env`
- 确认没有提交 `.local_secrets/`
- 确认没有提交数据库转储、账户数据、交易记录快照
- 检查 `README.md`、`SECURITY.md`、`DISCLAIMER.md` 是否符合你希望公开的边界

### 2. 仓库健康度

- `LICENSE` 已确认
- `CONTRIBUTING.md` 已确认
- `CODE_OF_CONDUCT.md` 已确认
- `SECURITY.md` 已确认
- Issue / PR 模板已确认
- GitHub Actions CI 可正常运行

### 3. 可复现性

- `.env.example` 可以独立启动
- `pip install -e .[dev]` 成功
- `pytest -q` 成功
- `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` 可启动

### 4. 版本与说明

- 更新 `CHANGELOG.md`
- 如有破坏性变更，在 README 中说明
- 如打标签发布，建议使用语义化版本号

## 推荐发布方式

### 方式一：直接上传到 GitHub 仓库

最简单，适合持续开发。

### 方式二：生成干净 zip 再上传 Release

```bash
python scripts/create_release_zip.py
```

输出：

```text
dist/trading-system-fastapi-github.zip
```

## 建议后续补充

- 前端界面或 CLI
- 更明确的 roadmap
- 集成测试与 Docker 化验收测试
- 更强的 secrets 管理与审计能力
