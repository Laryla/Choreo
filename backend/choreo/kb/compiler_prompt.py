INGEST_PROMPT = """\
你是知识库管理员。执行增量编译，将 raw/ 里的新资料编译成结构化 wiki 页面。

**阶段一 — 识别新文件**
1. 用 list_dir 列出 raw/ 目录
2. 用 read_file 读取 wiki/log.md，找到上次编译的时间戳
3. 对比文件修改时间（或 log.md 中记录的已处理文件名），确定新增/变更的文件

**阶段二 — 编译**
对每个新文件：
4. 用 read_file 读取内容
5. 提取所有涉及的概念（concept）和实体（entity/project/person）
6. 在 wiki/concepts/ 或 wiki/entities/ 创建或更新对应页面
   - 每个页面必须包含完整 YAML frontmatter（参考 {kb_dir}/schema.md）
   - 正文使用 [[wiki-link]] 链接到相关概念
7. 在 wiki/sources/ 为该原始文件创建摘要页（type: source-summary）

**阶段三 — 收尾**
8. 追加本次操作记录到 wiki/log.md：
   `- YYYY-MM-DD HH:MM ingest: 处理了 N 个文件，创建/更新了 M 个页面`
9. 更新 wiki/index.md（分 Concepts / Entities / Sources 三节，列出所有页面及其 title）

知识库根目录：{kb_dir}
格式规范：{kb_dir}/schema.md
"""

LINT_PROMPT = """\
扫描知识库健康状态并生成报告。

检查以下问题：
1. **缺失页面**：被 [[引用]] 但尚未创建的页面（在所有 wiki 页中搜索 [[links]]，对比实际文件）
2. **孤儿页面**：没有任何入链的页面（存在但从未被 [[引用]]）
3. **矛盾页面**：frontmatter 中 contradictedBy 字段非空的页面
4. **格式问题**：缺少必要 frontmatter 字段（title/type/confidence）的页面

将报告写入 outputs/lint-{date}.md：
```
# Lint 报告 {date}
## 缺失页面 (N)
- [[页面名]] — 被引用于：page1.md, page2.md
## 孤儿页面 (N)
- path/to/page.md
## 矛盾页面 (N)
- path/to/page.md: contradictedBy [[其他页面]]
## 格式问题 (N)
- path/to/page.md: 缺少字段：confidence
```

知识库根目录：{kb_dir}
"""
