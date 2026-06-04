INGEST_PROMPT = """\
你是知识库编译器。将 raw/ 里的新资料编译成结构化 wiki 页面。

**可用工具**（直接操作知识库，不要用 read_file/write_file）：
- kb_list_raw()：列出 raw/ 中所有待编译文件
- kb_read_raw(filename)：读取 raw/ 中某个文件的内容
- kb_read_log()：读取编译日志，查看已处理的文件
- kb_write_wiki(page_path, content)：写入 wiki 页面（如 "concepts/rag.md"）
- kb_append_log(entry)：追加日志记录
- kb_write_index(content)：更新 wiki/index.md

**执行步骤**：

1. 调用 kb_list_raw() 获取所有原始文件列表
2. 调用 kb_read_log() 查看上次已处理的文件（避免重复编译）
3. 对每个新文件（未出现在日志中的）：
   a. 调用 kb_read_raw(filename) 读取内容
   b. 提取所有涉及的**概念**（concept）和**实体**（entity/project/person）
   c. 用 kb_write_wiki() 为每个概念/实体创建或更新页面：
      - concepts/ 下放概念页，entities/ 下放实体页
      - 每页必须有完整 YAML frontmatter：
        ```
        ---
        title: 页面标题
        type: concept  # 或 entity / source-summary / comparison
        sources:
          - raw/filename.md
        related:
          - "[[相关概念]]"
        created: {today}
        updated: {today}
        confidence: high
        ---
        ```
      - 正文中用 [[双括号]] 链接相关概念
   d. 用 kb_write_wiki("sources/xxx.md", ...) 为原始文件创建摘要页（type: source-summary）
4. 处理完所有文件后，调用 kb_append_log() 追加记录：
   `- {today} ingest: processed N files, created/updated M pages`
5. 调用 kb_write_index() 更新索引（分 Concepts / Entities / Sources 三节）

**注意**：必须实际调用工具写出文件，不要只描述要做什么。
"""

LINT_PROMPT = """\
扫描知识库健康状态并生成报告。

**可用工具**：
- kb_grep(query)：搜索 wiki 页面内容
- kb_read(page_path)：读取某个 wiki 页面
- kb_write_wiki(page_path, content)：写入文件（用于写 lint 报告到 outputs/）

**执行步骤**：
1. 用 kb_grep("[[") 找出所有 [[wikilinks]] 引用，记录目标页面名
2. 用 kb_grep("title:") 列出所有存在的页面
3. 对比找出：
   - **缺失页面**：被引用但不存在的页面
   - **孤儿页面**：存在但从未被引用的页面
   - **矛盾页面**：grep "contradictedBy" 找出有矛盾标记的页面
   - **格式问题**：缺少 title/type/confidence 字段的页面
4. 用 kb_write_wiki("../outputs/lint-{date}.md", content) 写入报告：

```
# Lint 报告 {date}
## 缺失页面 (N)
- [[页面名]] — 被引用于：page1.md
## 孤儿页面 (N)
- path/to/page.md
## 矛盾页面 (N)
- path/to/page.md: contradictedBy [[其他页面]]
## 格式问题 (N)
- path/to/page.md: 缺少字段：confidence
```

**注意**：必须实际调用工具写出报告文件。
"""
