import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import ReactMarkdown from "react-markdown";
import Topbar from "@/components/Topbar/Topbar";
import {
  useRawFiles, useWikiList, useKBGraph, useKBLog, useWikiPage,
  useOutputs, useOutputFile,
  uploadRaw, triggerIngest, triggerLint, triggerProfileUpdate, triggerPullSources,
  type WikiPageMeta,
} from "@/hooks/useKnowledge";

type Tab = "wiki" | "graph" | "raw";

const TYPE_COLORS: Record<string, string> = {
  concept: "#6366f1",
  entity: "#f59e0b",
  "source-summary": "#10b981",
  comparison: "#ec4899",
};

function GraphView() {
  const { data } = useKBGraph();
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!data || !svgRef.current) return;
    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // edge.source = 文件路径（"concepts/rag.md"）
    // edge.target = wikilink 原始文本（"LlamaIndex"），需要映射到 node.id
    const labelToId = new Map(data.nodes.map((n) => [n.label, n.id]));
    const nodeIds = new Set(data.nodes.map((n) => n.id));
    const resolvedEdges = data.edges
      .map((e) => ({ source: e.source, target: labelToId.get(e.target) ?? e.target }))
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

    // 所有图形元素放入可变换的容器 g，支持平移和缩放
    const container = svg.append("g");

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => container.attr("transform", event.transform));

    svg.call(zoom).on("dblclick.zoom", null);

    const simulation = d3.forceSimulation(data.nodes as any)
      .force("link", d3.forceLink(resolvedEdges).id((d: any) => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const link = container.append("g").selectAll("line")
      .data(resolvedEdges).join("line")
      .attr("stroke", "#ccc").attr("stroke-width", 1);

    const node = container.append("g").selectAll("circle")
      .data(data.nodes).join("circle")
      .attr("r", 8)
      .attr("fill", (d) => TYPE_COLORS[d.type] ?? "#999")
      .attr("cursor", "grab")
      .call((d3.drag<SVGCircleElement, any>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      ) as any);

    const label = container.append("g").selectAll("text")
      .data(data.nodes).join("text")
      .text((d) => d.label)
      .attr("font-size", 11)
      .attr("fill", "#555")
      .attr("pointer-events", "none")
      .attr("dy", -12);

    // hover：实线高亮直连边，非直连边变虚线淡化
    const edgeId = (e: any) => ({
      s: typeof e.source === "object" ? e.source.id : e.source,
      t: typeof e.target === "object" ? e.target.id : e.target,
    });

    node
      .on("mouseenter", (_event, hovered: any) => {
        const connected = new Set<string>([hovered.id]);
        link.each((e: any) => {
          const { s, t } = edgeId(e);
          if (s === hovered.id || t === hovered.id) { connected.add(s); connected.add(t); }
        });

        link
          .attr("stroke", (e: any) => {
            const { s, t } = edgeId(e);
            return (s === hovered.id || t === hovered.id) ? "#6366f1" : "#ccc";
          })
          .attr("stroke-width", (e: any) => {
            const { s, t } = edgeId(e);
            return (s === hovered.id || t === hovered.id) ? 2 : 1;
          })
          .attr("stroke-dasharray", (e: any) => {
            const { s, t } = edgeId(e);
            return (s === hovered.id || t === hovered.id) ? null : "5,4";
          })
          .attr("stroke-opacity", (e: any) => {
            const { s, t } = edgeId(e);
            return (s === hovered.id || t === hovered.id) ? 1 : 0.2;
          });

        node.attr("opacity", (n: any) => connected.has(n.id) ? 1 : 0.2);
        label.attr("opacity", (n: any) => connected.has(n.id) ? 1 : 0.2);
      })
      .on("mouseleave", () => {
        link
          .attr("stroke", "#ccc")
          .attr("stroke-width", 1)
          .attr("stroke-dasharray", null)
          .attr("stroke-opacity", 1);
        node.attr("opacity", 1);
        label.attr("opacity", 1);
      });

    simulation.on("tick", () => {
      link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });

    return () => { simulation.stop(); };
  }, [data]);

  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[#aaa]">
        暂无知识图谱，请先上传资料并触发编译
      </div>
    );
  }
  return <svg ref={svgRef} className="w-full h-full" style={{ cursor: "move" }} />;
}

function WikiView() {
  const { data: pages } = useWikiList();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const { data: page } = useWikiPage(selectedPath);

  return (
    <div className="flex h-full">
      <div className="w-56 flex-shrink-0 border-r border-[#e6e2da] dark:border-[#2a2a2a] overflow-y-auto p-3">
        {!pages || pages.length === 0 ? (
          <p className="text-xs text-[#aaa] px-2 py-4">暂无 wiki 页面</p>
        ) : (
          pages.map((p: WikiPageMeta) => (
            <button
              key={p.path}
              onClick={() => setSelectedPath(p.path)}
              className={`w-full text-left text-xs px-2 py-1.5 rounded hover:bg-[#e6e2da] dark:hover:bg-[#1e1e1e] truncate ${
                selectedPath === p.path
                  ? "bg-[#e6e2da] dark:bg-[#1e1e1e] font-medium"
                  : "text-[#666]"
              }`}
            >
              {p.name}
            </button>
          ))
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {page ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown>{page.content}</ReactMarkdown>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-[#aaa]">
            ← 选择左侧页面查看内容
          </div>
        )}
      </div>
    </div>
  );
}

function RawView() {
  const { data: files } = useRawFiles();
  const { data: log } = useKBLog();
  const { data: outputs } = useOutputs();
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [profiling, setProfiling] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const { data: report } = useOutputFile(selectedReport);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadRaw(file);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleIngest = async () => {
    setIngesting(true);
    try {
      await triggerIngest();
    } finally {
      setTimeout(() => setIngesting(false), 2000);
    }
  };

  const handleLint = async () => {
    await triggerLint();
  };

  const handleUpdateProfile = async () => {
    setProfiling(true);
    try {
      await triggerProfileUpdate();
    } finally {
      setProfiling(false);
    }
  };

  const handlePullSources = async () => {
    setPulling(true);
    try {
      await triggerPullSources();
    } finally {
      setTimeout(() => setPulling(false), 2000);
    }
  };

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div className="flex items-center gap-3">
        <label className="text-xs px-3 py-1.5 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] cursor-pointer hover:opacity-80">
          {uploading ? "上传中…" : "上传文件（PDF/DOCX/MD…）"}
          <input type="file" accept=".md,.txt,.pdf,.docx,.pptx,.xlsx,.html,.htm,.csv,.json,.xml" className="hidden" onChange={handleUpload} />
        </label>
        <button
          onClick={handleIngest}
          disabled={ingesting}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#6366f1] text-white hover:opacity-90 disabled:opacity-50"
        >
          {ingesting ? "编译中…" : "触发编译"}
        </button>
        <button
          onClick={handleLint}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] hover:opacity-80"
        >
          Lint 检查
        </button>
        <button
          onClick={handlePullSources}
          disabled={pulling}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#10b981] text-white hover:opacity-90 disabled:opacity-50"
        >
          {pulling ? "拉取中…" : "拉取外部源"}
        </button>
        <button
          onClick={handleUpdateProfile}
          disabled={profiling}
          className="text-xs px-3 py-1.5 rounded-lg bg-purple-600 text-white hover:opacity-90 disabled:opacity-50"
        >
          {profiling ? "更新中…" : "更新用户画像"}
        </button>
      </div>
      <div className="flex gap-4 flex-1 min-h-0">
        {/* 原始资料列表 */}
        <div className="w-48 flex-shrink-0 overflow-y-auto">
          <p className="text-xs font-medium text-[#888] mb-2">
            原始资料（{files?.length ?? 0} 个）
          </p>
          {files?.map((f) => (
            <div
              key={f.name}
              className="text-xs py-1.5 border-b border-[#e6e2da] dark:border-[#2a2a2a] text-[#555] dark:text-[#888]"
            >
              {f.name}
              <span className="text-[#aaa] ml-1">({(f.size / 1024).toFixed(1)}K)</span>
            </div>
          ))}
        </div>

        {/* 编译日志 */}
        <div className="w-56 flex-shrink-0 overflow-y-auto border-l border-[#e6e2da] dark:border-[#2a2a2a] pl-4">
          <p className="text-xs font-medium text-[#888] mb-2">编译日志</p>
          <pre className="text-[10px] text-[#666] dark:text-[#555] whitespace-pre-wrap">
            {log?.content || "暂无日志"}
          </pre>
        </div>

        {/* Lint 报告 */}
        <div className="flex-1 flex flex-col min-h-0 border-l border-[#e6e2da] dark:border-[#2a2a2a] pl-4">
          <p className="text-xs font-medium text-[#888] mb-2">
            Lint 报告（{outputs?.length ?? 0} 份）
          </p>
          {!outputs || outputs.length === 0 ? (
            <p className="text-xs text-[#aaa]">暂无报告，点击「Lint 检查」生成</p>
          ) : (
            <div className="flex flex-col gap-1 mb-3">
              {outputs.map((o) => (
                <button
                  key={o.name}
                  onClick={() => setSelectedReport(o.name)}
                  className={`text-left text-xs px-2 py-1.5 rounded truncate transition-colors ${
                    selectedReport === o.name
                      ? "bg-[#e6e2da] dark:bg-[#1e1e1e] font-medium text-[#333] dark:text-[#ccc]"
                      : "text-[#666] hover:bg-[#e6e2da] dark:hover:bg-[#1e1e1e]"
                  }`}
                >
                  {o.name}
                </button>
              ))}
            </div>
          )}
          {report && (
            <div className="flex-1 overflow-y-auto border-t border-[#e6e2da] dark:border-[#2a2a2a] pt-3">
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown>{report.content}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("wiki");

  const tabs: { id: Tab; label: string }[] = [
    { id: "wiki", label: "Wiki 浏览" },
    { id: "graph", label: "知识图谱" },
    { id: "raw", label: "原始资料" },
  ];

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="知识库" />
      <div className="flex gap-0 border-b border-[#e6e2da] dark:border-[#2a2a2a] px-6">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-xs px-4 py-2.5 border-b-2 transition-colors ${
              tab === t.id
                ? "border-[#6366f1] text-[#6366f1]"
                : "border-transparent text-[#888] hover:text-[#555]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === "wiki" && <WikiView />}
        {tab === "graph" && <GraphView />}
        {tab === "raw" && <RawView />}
      </div>
    </div>
  );
}
