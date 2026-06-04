from pathlib import Path
import textwrap

DEFAULT_SCHEMA = textwrap.dedent("""\
    # 知识库 Schema

    ## 页面规范
    每个 wiki 页面必须包含 YAML frontmatter：
    ```yaml
    ---
    title: 页面标题
    type: concept | entity | source-summary | comparison
    sources:
      - raw/filename.md
    related:
      - "[[相关概念]]"
    created: YYYY-MM-DD
    updated: YYYY-MM-DD
    confidence: high | medium | low
    ---
    ```
    文件名：使用 kebab-case 英文，例如 `project-choreo.md`。
    内部链接：使用 `[[页面标题]]` 格式。

    ## 页面类型
    - **concept**：理论、技术、方法（如"RAG 检索"）
    - **entity**：人物、项目、组织（如"Choreo 项目"）
    - **source-summary**：一个原始资料文件的摘要
    - **comparison**：多个概念/方案的对比分析

    ## 编译规则
    1. 永远不要修改 raw/ 中的文件
    2. 每次操作都追加到 wiki/log.md
    3. 遇到矛盾时，在 frontmatter 中添加 `contradictedBy: ["[[其他页面]]"]`——不要自动合并
    """)


def kb_init(kb_dir: str) -> None:
    root = Path(kb_dir)
    for subdir in [
        "raw",
        "wiki/concepts",
        "wiki/entities",
        "wiki/sources",
        "wiki/comparisons",
        "outputs",
    ]:
        (root / subdir).mkdir(parents=True, exist_ok=True)

    schema_path = root / "schema.md"
    if not schema_path.exists():
        schema_path.write_text(DEFAULT_SCHEMA, encoding="utf-8")

    log_path = root / "wiki" / "log.md"
    if not log_path.exists():
        log_path.write_text("# 知识库日志\n\n", encoding="utf-8")

    index_path = root / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text("# 知识库索引\n\n", encoding="utf-8")
