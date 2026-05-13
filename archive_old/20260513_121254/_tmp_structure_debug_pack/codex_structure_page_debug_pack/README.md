# Codex Debug Pack — Structure Page Blank Chart

本包用于让 Codex 快速理解当前仓库问题、判断为什么“形态叠加图”页面不显示图表，并按低风险顺序实施修复。

## 包含内容
- `01_repo_audit_and_workflow_optimization.md`：代码问题审计与建议工作流
- `02_blank_chart_root_cause_analysis.md`：为什么该页面不显示图表
- `03_structure_page_fix_spec.md`：建议的修复方案与模块拆分
- `04_target_files_and_changes.json`：需要修改的文件清单
- `05_acceptance_and_debug_checklist.md`：联调与验收清单
- `audit_duplicate_js_functions.py`：快速扫描 `app/static/app.js` 中重复函数定义

## 结论摘要
1. 当前上传仓库里 **没有正式接入的 Structure 页面**：
   - `app/web/router.py` 中没有 `/structure-page`
   - `app/templates/page.html` 中没有 `structure-template`
   - `app/api/router.py` 中没有 structure router
   - `app/` 下没有 `structure` 相关 service / schema / repository / DB table
2. 因此，从这份已上传代码本身看，截图中的“形态叠加图”页面不是一个已完整接线的正式功能，极大概率是：
   - 本地未提交代码
   - 临时静态页面
   - 或前端壳子已做出来，但没有 API / boot / renderer 接上
3. `app/static/app.js` 过大且重复拼接严重，已经足以造成：
   - 初始化流程不透明
   - 定时器与事件绑定重复
   - 页面接线容易丢失
   - 图表页出问题时难以排查

## 建议修复顺序
1. 先建立正式的 structure page 页面接线（route/template/bootstrap/API 协议）
2. 再接 structure snapshot 假数据/静态数据，确保页面至少能出图
3. 最后再接真实结构识别结果

## 不建议
- 不要继续把新页面逻辑塞进同一个超长 `app/static/app.js`
- 不要先做复杂识别逻辑，再回头补页面接线
- 不要让空数据、库加载失败、page_id 不匹配时保持“静默白屏”
