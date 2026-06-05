# 知识库页面重设计 Spec

**日期**: 2026-06-05
**状态**: 待实现

---

## 背景与问题

现有 `KnowledgePage` 存在四个核心痛点：

1. **信息架构割裂** — 三个 Tab（Wiki / 图谱 / 原始资料）相互孤立，无法统一浏览
2. **视觉层次缺失** — 全灰小字，无卡片层次，Wiki 侧边栏文件列表过于简陋
3. **操作区杂乱** — 原始资料 Tab 内五个按钮横排堆叠，主次不分
4. **内容不可发现** — 无全局搜索，Wiki 列表仅展示文件名，无摘要/标签

---

## 设计决策

| 维度 | 决策 |
|------|------|
| 布局结构 | **统一主页 + 过滤视图**（取消 Tab，全部内容混排，过滤器切换） |
| 详情展示 | **右侧滑入面板**（主网格缩窄但保持可见，可快速切换条目） |
| 主题 | **双模式跟随项目**，沿用 `#f5f2eb` light / `#141414` dark 色系，不单独定义新色板 |

---

## 页面结构

```
┌─────────────────────────────────────────────────┐
│ 知识库         你的个人知识图谱 · 12篇 · 8份     │  ← PageHeader
├─────────────────────────────────────────────────┤
│ 🔍 搜索概念、文章、原始资料…                     │  ← SearchBar
├─────────────────────────────────────────────────┤
│ [全部][Wiki][原始资料][图谱视图]   [操作区 →]    │  ← FilterBar
├───────────────────────────┬─────────────────────┤
│                           │                     │
│  卡片网格（主区域）         │  详情面板（滑入）    │
│  Wiki 条目 + 原始资料混排  │  Markdown 内容      │
│                           │  + 引用来源列表      │
└───────────────────────────┴─────────────────────┘
```

---

## 组件规格

### 1. PageHeader

- 标题：`知识库`（font-weight 700，跟随主题色）
- 副标题：`{wikiCount} 篇 Wiki · {rawCount} 份原始资料`（小字，`text-[#888]`）

### 2. SearchBar

- 全宽输入框，圆角 `rounded-xl`，内嵌搜索图标
- 搜索范围覆盖 Wiki 标题、正文摘要、原始资料文件名
- 输入时实时过滤卡片网格（客户端过滤，无需新增 API）
- focus 时边框高亮 `#6366f1`

### 3. FilterBar

左侧过滤器（胶囊按钮组，选中态 `bg-[#6366f1] text-white`）：
- **全部** — 展示所有卡片
- **Wiki** — 仅展示 `WikiPageMeta` 卡片
- **原始资料** — 仅展示 `RawFile` 卡片
- **图谱视图** — 替换网格区域为现有 `GraphView` D3 组件

右侧操作区（紧凑文字按钮，次要样式）：
- `📥 上传` — 触发文件 input，同现有 `uploadRaw`
- `🔗 拉取外部源` — 调用 `triggerPullSources`
- `✓ Lint` — 调用 `triggerLint`
- `👤 更新画像` — 调用 `triggerProfileUpdate`
- `⚡ 触发编译` — 调用 `triggerIngest`，**Primary 样式**（`bg-[#6366f1] text-white`）

操作按钮 loading 态：禁用 + 文字变为 `…` 后缀，同现有实现。

### 4. 卡片网格（KnowledgeGrid）

- CSS Grid，`grid-cols-[repeat(auto-fill,minmax(220px,1fr))]`，gap-3
- 按内容类型分节：Wiki 在上，原始资料在下（或按 modified_at 混合排序，filter 选中时只显示对应类型）
- 节头：小号全大写标签行（`text-[#aaa] uppercase text-xs`）

**WikiCard** 字段：
- 类型 Badge：`📖 Wiki`，`bg-[#eef2ff] text-[#6366f1]`（dark: `bg-indigo-900/20 text-indigo-400`）
- 分类标签（来自 frontmatter `type` 字段）：concept / entity / source-summary / comparison，沿用 `TYPE_COLORS`
- 标题（font-semibold）
- 摘要（文件正文前 80 字，两行截断）—— **需新增 API 字段 `summary`**
- 元数据行：`🔗 {refCount} 个来源 · {relativeTime}`

**RawFileCard** 字段：
- 类型 Badge：按文件扩展名显示 `PDF / MD / DOCX…`
- 文件名（font-semibold）
- 摘要（可选，若无则显示文件路径）
- 元数据行：状态圆点（已编译 `#10b981` / 待编译 `#f59e0b`）+ `{size}KB`

**选中态**：`border-[#6366f1] ring-1 ring-[#6366f1]`

### 5. 详情面板（DetailPanel）

- 宽度：`w-96`（384px），fixed 右侧，flex-shrink-0
- 面板头：标题 + 关闭按钮（`✕`）
- 元数据行：类型 badge + 分类标签 + 更新时间
- 内容区：`ReactMarkdown`，`prose prose-sm dark:prose-invert`，可滚动
- 底部引用来源列表（仅 WikiCard 有）：显示关联的原始资料文件名

**触发与关闭**：
- 点击任意卡片 → 设置 `selectedItem`，面板从右侧以 `translateX` 动画滑入（`transition-transform duration-200`）
- 点击 `✕` 或点击已选中卡片 → 关闭面板，`translateX(100%)`
- 关闭时主网格恢复全宽

### 6. 图谱视图

- 复用现有 `GraphView` 组件，整体替换主区域
- 面板不显示（图谱模式下无详情面板）

---

## 数据层变更

### 需新增 API 字段

`GET /api/kb/wiki/` 返回的 `WikiPageMeta` 需增加：

```python
class WikiPageMeta(BaseModel):
    path: str
    name: str
    modified_at: float
    summary: str        # 新增：正文前 80 字
    type: str           # 新增：concept / entity / source-summary / comparison
    ref_count: int      # 新增：引用来源数量
```

后端从 Markdown frontmatter 读取 `type`，从正文截取 `summary`，从 wikilink 计数得到 `ref_count`。

`RawFile` 无需变更，现有 `name / size / modified_at` 足够。

### 编译状态

原始资料"已编译"状态：通过检查 `wiki/` 目录下是否存在以该文件名为来源的页面判断，或在 `RawFile` 中新增 `compiled: bool` 字段（推荐）。

---

## 前端文件变更范围

| 文件 | 变更类型 |
|------|---------|
| `frontend/src/pages/KnowledgePage.tsx` | **重写**（主结构） |
| `frontend/src/hooks/useKnowledge.ts` | **小改**（更新 `WikiPageMeta` 类型） |
| `frontend/src/components/Knowledge/WikiCard.tsx` | **新建** |
| `frontend/src/components/Knowledge/RawFileCard.tsx` | **新建** |
| `frontend/src/components/Knowledge/DetailPanel.tsx` | **新建** |
| `frontend/src/components/Knowledge/KnowledgeGrid.tsx` | **新建** |
| `backend/choreo/gateway/routers/knowledge.py` | **小改**（WikiPageMeta 增加字段） |

---

## 不在本次范围内

- Wiki 内容编辑（只读浏览）
- 搜索后端 API（客户端过滤已足够当前数据量）
- 图谱视图重设计（复用现有 D3 实现）
- 引用来源的跳转导航

---

## 验收标准

1. 知识库页面在 light / dark 两个模式下视觉均合格，跟随 `useTheme`
2. 全局搜索框可实时过滤 Wiki 和原始资料卡片
3. 过滤器 Tab 切换正常，图谱视图可替换主区域
4. 点击 Wiki 卡片触发右侧详情面板，展示 Markdown 内容和引用来源
5. 五个操作按钮功能与现有一致，loading 态正常
6. 原有 `GraphView` 复用无回归
