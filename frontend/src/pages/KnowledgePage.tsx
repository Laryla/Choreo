import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import Topbar from "@/components/Topbar/Topbar";
import KnowledgeGrid from "@/components/Knowledge/KnowledgeGrid";
import DetailPanel from "@/components/Knowledge/DetailPanel";
import {
  useRawFiles, useWikiList, useKBGraph,
  uploadRaw, triggerIngest, triggerLint, triggerProfileUpdate, triggerPullSources,
  type WikiPageMeta, type RawFile,
} from "@/hooks/useKnowledge";

type Filter = "all" | "wiki" | "raw" | "graph";
type SelectedItem = { kind: "wiki"; data: WikiPageMeta } | { kind: "raw"; data: RawFile };

// ---- GraphView（内联复用，无需改动）----
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

    const labelToId = new Map(data.nodes.map((n) => [n.label, n.id]));
    const nodeIds = new Set(data.nodes.map((n) => n.id));
    const resolvedEdges = data.edges
      .map((e) => ({ source: e.source, target: labelToId.get(e.target) ?? e.target }))
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

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
        .on("start", (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      ) as any);

    const label = container.append("g").selectAll("text")
      .data(data.nodes).join("text")
      .text((d) => d.label)
      .attr("font-size", 11).attr("fill", "#555").attr("pointer-events", "none").attr("dy", -12);

    const edgeId = (e: any) => ({
      s: typeof e.source === "object" ? e.source.id : e.source,
      t: typeof e.target === "object" ? e.target.id : e.target,
    });

    node
      .on("mouseenter", (_event, hovered: any) => {
        const connected = new Set<string>([hovered.id]);
        link.each((e: any) => { const { s, t } = edgeId(e); if (s === hovered.id || t === hovered.id) { connected.add(s); connected.add(t); } });
        link.attr("stroke", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? "#6366f1" : "#ccc"; })
            .attr("stroke-width", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? 2 : 1; })
            .attr("stroke-dasharray", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? null : "5,4"; })
            .attr("stroke-opacity", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? 1 : 0.2; });
        node.attr("opacity", (n: any) => connected.has(n.id) ? 1 : 0.2);
        label.attr("opacity", (n: any) => connected.has(n.id) ? 1 : 0.2);
      })
      .on("mouseleave", () => {
        link.attr("stroke", "#ccc").attr("stroke-width", 1).attr("stroke-dasharray", null).attr("stroke-opacity", 1);
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
      <div className="flex items-center justify-center h-full text-sm text-[#aaa] dark:text-[#475569]">
        暂无知识图谱，请先上传资料并触发编译
      </div>
    );
  }
  return <svg ref={svgRef} className="w-full h-full" style={{ cursor: "move" }} />;
}
// ---- /GraphView ----

export default function KnowledgePage() {
  const { data: wikiPages = [] } = useWikiList();
  const { data: rawFiles = [] } = useRawFiles();

  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null);

  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [linting, setLinting] = useState(false);
  const [profiling, setProfiling] = useState(false);
  const [pulling, setPulling] = useState(false);

  const handleSelectWiki = (page: WikiPageMeta) => {
    setSelectedItem((prev) =>
      prev?.kind === "wiki" && prev.data.path === page.path ? null : { kind: "wiki", data: page }
    );
  };

  const handleSelectRaw = (file: RawFile) => {
    setSelectedItem((prev) =>
      prev?.kind === "raw" && prev.data.name === file.name ? null : { kind: "raw", data: file }
    );
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try { await uploadRaw(file); } finally { setUploading(false); e.target.value = ""; }
  };

  const handleIngest = async () => {
    setIngesting(true);
    try { await triggerIngest(); } finally { setTimeout(() => setIngesting(false), 2000); }
  };

  const handleLint = async () => {
    setLinting(true);
    try { await triggerLint(); } finally { setTimeout(() => setLinting(false), 2000); }
  };

  const handlePullSources = async () => {
    setPulling(true);
    try { await triggerPullSources(); } finally { setTimeout(() => setPulling(false), 2000); }
  };

  const handleUpdateProfile = async () => {
    setProfiling(true);
    try { await triggerProfileUpdate(); } finally { setProfiling(false); }
  };

  const FILTERS: { id: Filter; label: string }[] = [
    { id: "all", label: "全部" },
    { id: "wiki", label: "Wiki" },
    { id: "raw", label: "原始资料" },
    { id: "graph", label: "图谱视图" },
  ];

  const btnBase =
    "text-xs px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-50";
  const btnSecondary =
    `${btnBase} bg-[#ede9e0] dark:bg-[#22223a] border-[#d6d0c7] dark:border-[#3a3a55] text-[#555] dark:text-[#94a3b8] hover:bg-[#e0dbd0] dark:hover:bg-[#2d2d50]`;
  const btnPrimary =
    `${btnBase} bg-[#6366f1] border-[#6366f1] text-white hover:bg-[#5558e8]`;

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="知识库" />

      {/* Header */}
      <div className="px-6 pt-4 pb-2">
        <h1 className="text-lg font-bold text-[#1a1a1a] dark:text-[#e2e8f0]">知识库</h1>
        <p className="text-xs text-[#888] dark:text-[#475569] mt-0.5">
          {wikiPages.length} 篇 Wiki · {rawFiles.length} 份原始资料
        </p>
      </div>

      {/* Search */}
      <div className="px-6 pb-3">
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#aaa] dark:text-[#475569] text-sm pointer-events-none">
            🔍
          </span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索概念、文章、原始资料…"
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-[#d6d0c7] dark:border-[#3a3a55] bg-white dark:bg-[#16162a] text-sm text-[#333] dark:text-[#e2e8f0] placeholder-[#aaa] dark:placeholder-[#475569] outline-none focus:border-[#6366f1] transition-colors"
          />
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-1.5 px-6 pb-3 border-b border-[#e6e2da] dark:border-[#2a2a2a]">
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => { setFilter(f.id); setSelectedItem(null); }}
              className={`text-xs px-3 py-1.5 rounded-full font-medium transition-colors ${
                filter === f.id
                  ? "bg-[#6366f1] text-white"
                  : "text-[#888] dark:text-[#64748b] hover:text-[#333] dark:hover:text-[#e2e8f0] hover:bg-[#e6e2da] dark:hover:bg-[#2d2d48]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <label className={`${btnSecondary} cursor-pointer`}>
            {uploading ? "上传中…" : "📥 上传"}
            <input
              type="file"
              accept=".md,.txt,.pdf,.docx,.pptx,.xlsx,.html,.htm,.csv,.json,.xml"
              className="hidden"
              onChange={handleUpload}
            />
          </label>
          <button onClick={handlePullSources} disabled={pulling} className={btnSecondary}>
            {pulling ? "拉取中…" : "🔗 拉取外部源"}
          </button>
          <button onClick={handleLint} disabled={linting} className={btnSecondary}>
            {linting ? "检查中…" : "✓ Lint"}
          </button>
          <button onClick={handleUpdateProfile} disabled={profiling} className={btnSecondary}>
            {profiling ? "更新中…" : "👤 更新画像"}
          </button>
          <button onClick={handleIngest} disabled={ingesting} className={btnPrimary}>
            {ingesting ? "编译中…" : "⚡ 触发编译"}
          </button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {filter === "graph" ? (
          <div className="flex-1 overflow-hidden">
            <GraphView />
          </div>
        ) : (
          <>
            <KnowledgeGrid
              wikiPages={wikiPages}
              rawFiles={rawFiles}
              filter={filter as "all" | "wiki" | "raw"}
              query={query}
              selectedItem={selectedItem}
              onSelectWiki={handleSelectWiki}
              onSelectRaw={handleSelectRaw}
            />
            <DetailPanel
              item={selectedItem}
              onClose={() => setSelectedItem(null)}
            />
          </>
        )}
      </div>
    </div>
  );
}
