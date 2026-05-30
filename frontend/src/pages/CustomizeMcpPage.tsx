// frontend/src/pages/CustomizeMcpPage.tsx
import { useState, useRef } from "react";
import useSWR from "swr";
import type { McpServer, McpServerCreate, McpServerPatch, ToolConfig } from "@/api/mcp";
import { listServers, createServer, patchServer, deleteServer, reloadServers } from "@/api/mcp";

// ── Preset marketplace servers ────────────────────────────────────────────────

const PRESETS: Array<{
  name: string; icon: string; label: string; desc: string; official: boolean;
  transport: "stdio"; command: string; args: string[]; env_keys: string[];
}> = [
  { name: "github", icon: "🐙", label: "GitHub", desc: "仓库、Issues、PR、Code Search", official: true, transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-github"], env_keys: ["GITHUB_PERSONAL_ACCESS_TOKEN"] },
  { name: "postgres", icon: "🐘", label: "PostgreSQL", desc: "查询、Schema 管理、事务", official: true, transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-postgres"], env_keys: ["POSTGRES_CONNECTION_STRING"] },
  { name: "filesystem", icon: "🗂️", label: "Filesystem", desc: "本地文件系统读写", official: true, transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed"], env_keys: [] },
  { name: "brave-search", icon: "🔍", label: "Brave Search", desc: "实时网页搜索", official: true, transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-brave-search"], env_keys: ["BRAVE_API_KEY"] },
  { name: "slack", icon: "💬", label: "Slack", desc: "消息收发、频道管理", official: true, transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-slack"], env_keys: ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"] },
  { name: "notion", icon: "📝", label: "Notion", desc: "页面读写、数据库查询", official: false, transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-notion"], env_keys: ["NOTION_API_TOKEN"] },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

const APPROVAL_LABELS: Record<string, string> = {
  auto: "自动允许", confirm: "需要确认", deny: "禁用",
};

function buildJsonConfig(s: McpServer): string {
  const obj: Record<string, unknown> = { command: s.command };
  if (s.args?.length) obj.args = s.args;
  if (Object.keys(s.env).length) obj.env = s.env;
  if (s.transport !== "stdio") obj.url = s.url;
  return JSON.stringify({ mcpServers: { [s.name]: obj } }, null, 2);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusDot({ enabled }: { enabled: boolean }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0
      ${enabled ? "bg-emerald-500 shadow-[0_0_0_2px_rgba(34,197,94,.2)]" : "bg-[#ccc] dark:bg-[#444]"}`} />
  );
}

function Toggle({ on, onToggle, disabled }: { on: boolean; onToggle: () => void; disabled?: boolean }) {
  return (
    <button
      role="switch" aria-checked={on} onClick={onToggle} disabled={disabled}
      className={`relative inline-flex h-[22px] w-[40px] flex-shrink-0 rounded-full transition-colors duration-200 disabled:opacity-40
        ${on ? "bg-[#1e90ff]" : "bg-[#d1d5db] dark:bg-[#3a3a3a]"}`}
    >
      <span className={`inline-block h-[16px] w-[16px] mt-[3px] transform rounded-full bg-white shadow-sm transition-transform duration-200
        ${on ? "translate-x-[21px]" : "translate-x-[3px]"}`} />
    </button>
  );
}

// ── Add Server Modal ──────────────────────────────────────────────────────────

interface AddModalProps {
  onClose: () => void;
  onCreated: (s: McpServer) => void;
  installed: Set<string>;
}

function AddServerModal({ onClose, onCreated, installed }: AddModalProps) {
  const [mode, setMode] = useState<"form" | "json" | "market">("form");
  const [transport, setTransport] = useState<"stdio" | "sse" | "http">("stdio");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [url, setUrl] = useState("");
  const [envRows, setEnvRows] = useState<[string, string][]>([["", ""]]);
  const [jsonText, setJsonText] = useState(`{\n  "mcpServers": {\n    "my-server": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-xxx"],\n      "env": {}\n    }\n  }\n}`);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const addEnvRow = () => setEnvRows((r) => [...r, ["", ""]]);
  const setEnvKey = (i: number, v: string) => setEnvRows((r) => r.map((row, idx) => idx === i ? [v, row[1]] : row));
  const setEnvVal = (i: number, v: string) => setEnvRows((r) => r.map((row, idx) => idx === i ? [row[0], v] : row));
  const delEnvRow = (i: number) => setEnvRows((r) => r.filter((_, idx) => idx !== i));

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      let body: McpServerCreate;
      if (mode === "json") {
        const parsed = JSON.parse(jsonText);
        const servers = parsed.mcpServers ?? parsed;
        const [sName, sCfg] = Object.entries(servers)[0] as [string, any];
        body = { name: sName, transport: sCfg.url ? "sse" : "stdio", command: sCfg.command, args: sCfg.args, url: sCfg.url, env: sCfg.env ?? {} };
      } else {
        if (!name.trim()) { setError("名称不能为空"); return; }
        const env: Record<string, string> = {};
        envRows.forEach(([k, v]) => { if (k.trim()) env[k.trim()] = v; });
        body = { name: name.trim(), transport, command: transport === "stdio" ? command : undefined, url: transport !== "stdio" ? url : undefined, env };
      }
      const created = await createServer(body);
      onCreated(created);
      onClose();
    } catch (e: any) {
      setError(e.message ?? "创建失败");
    } finally {
      setBusy(false);
    }
  };

  const installPreset = async (preset: typeof PRESETS[0]) => {
    setBusy(true);
    try {
      const created = await createServer({ name: preset.name, transport: preset.transport, command: preset.command, args: preset.args });
      onCreated(created);
    } catch (e: any) {
      setError(e.message ?? "安装失败");
    } finally {
      setBusy(false);
    }
  };

  const filtered = PRESETS.filter((p) => p.label.toLowerCase().includes(q.toLowerCase()) || p.desc.includes(q));

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 backdrop-blur-sm" onClick={onClose}>
      <div className="w-[560px] max-h-[88vh] bg-white dark:bg-[#1a1a1a] rounded-2xl border border-[#e5e1d8] dark:border-[#252525] flex flex-col overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-[#f0ede6] dark:border-[#222]">
          <h2 className="text-[15px] font-semibold text-[#1e293b] dark:text-[#e8e8e8]">添加 MCP Server</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-[#bbb] hover:text-[#555] hover:bg-[#f5f2eb] dark:hover:bg-[#222] transition-colors">
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 3l10 10M13 3L3 13"/></svg>
          </button>
        </div>

        {/* Mode tabs */}
        <div className="flex mx-6 mt-4 mb-0 rounded-xl overflow-hidden border border-[#e5e1d8] dark:border-[#252525]">
          {(["form", "json", "market"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)}
              className={`flex-1 py-2 text-[12px] font-medium transition-colors
                ${mode === m ? "bg-[#1e293b] dark:bg-[#2a2a2a] text-white" : "text-[#888] hover:bg-[#f5f2eb] dark:hover:bg-[#222]"}`}>
              {m === "form" ? "表单" : m === "json" ? "JSON" : "市场"}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* Form mode */}
          {mode === "form" && (
            <div className="space-y-4">
              <div>
                <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-1.5">Server 名称</label>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 my-database"
                  className="w-full px-3 py-2 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] text-[12.5px] text-[#1e293b] dark:text-[#e8e8e8] outline-none focus:border-[#1e90ff]" />
              </div>
              <div>
                <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-1.5">传输协议</label>
                <div className="flex gap-2">
                  {(["stdio", "sse", "http"] as const).map((t) => (
                    <button key={t} onClick={() => setTransport(t)}
                      className={`flex-1 py-1.5 rounded-lg text-[11.5px] font-medium border transition-colors
                        ${transport === t ? "bg-[#1e293b] dark:bg-[#2a2a2a] text-white border-[#1e293b]" : "border-[#e5e1d8] dark:border-[#252525] text-[#888] hover:bg-[#f5f2eb] dark:hover:bg-[#222]"}`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              {transport === "stdio" ? (
                <div>
                  <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-1.5">启动命令</label>
                  <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx @modelcontextprotocol/server-xxx"
                    className="w-full px-3 py-2 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] text-[12px] font-mono text-[#1e293b] dark:text-[#e8e8e8] outline-none focus:border-[#1e90ff]" />
                </div>
              ) : (
                <div>
                  <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-1.5">Server URL</label>
                  <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-mcp-server.com/mcp"
                    className="w-full px-3 py-2 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] text-[12px] font-mono text-[#1e293b] dark:text-[#e8e8e8] outline-none focus:border-[#1e90ff]" />
                </div>
              )}
              <div>
                <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-1.5">环境变量</label>
                <div className="space-y-2">
                  {envRows.map(([k, v], i) => (
                    <div key={i} className="flex gap-2 items-center">
                      <input value={k} onChange={(e) => setEnvKey(i, e.target.value)} placeholder="KEY"
                        className="flex-1 px-3 py-1.5 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] text-[11.5px] font-mono text-[#1e293b] dark:text-[#e8e8e8] outline-none" />
                      <input value={v} onChange={(e) => setEnvVal(i, e.target.value)} placeholder="VALUE" type="password"
                        className="flex-[2] px-3 py-1.5 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] text-[11.5px] font-mono text-[#1e293b] dark:text-[#e8e8e8] outline-none" />
                      <button onClick={() => delEnvRow(i)} className="p-1.5 rounded-lg text-[#ccc] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors">
                        <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 4h10M6 4V3h4v1M5 4l.5 9h5L11 4"/></svg>
                      </button>
                    </div>
                  ))}
                  <button onClick={addEnvRow} className="text-[11.5px] text-[#aaa] hover:text-[#555] dark:hover:text-[#ccc] flex items-center gap-1 transition-colors">
                    <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 2v12M2 8h12"/></svg>
                    添加变量
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* JSON mode */}
          {mode === "json" && (
            <div>
              <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-1.5">JSON 配置</label>
              <textarea value={jsonText} onChange={(e) => setJsonText(e.target.value)} rows={14}
                className="w-full px-4 py-3 rounded-xl border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#0e0e0e] text-[11.5px] font-mono text-[#444] dark:text-[#aaa] leading-relaxed outline-none focus:border-[#1e90ff] resize-none" />
              <p className="text-[11px] text-[#bbb] mt-2">粘贴标准 MCP server JSON 配置，支持 stdio / SSE / HTTP 格式</p>
            </div>
          )}

          {/* Market mode */}
          {mode === "market" && (
            <div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] mb-4">
                <svg className="w-3.5 h-3.5 text-[#bbb]" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="6.5" cy="6.5" r="4"/><path d="M11 11l2.5 2.5"/></svg>
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索 MCP Server…"
                  className="flex-1 bg-transparent text-[12px] text-[#1e293b] dark:text-[#e8e8e8] placeholder-[#bbb] outline-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                {filtered.map((p) => {
                  const isInstalled = installed.has(p.name);
                  return (
                    <div key={p.name} className="p-4 rounded-xl border border-[#e5e1d8] dark:border-[#252525] bg-white dark:bg-[#111] hover:border-[#1e90ff] transition-colors">
                      <div className="text-2xl mb-2">{p.icon}</div>
                      <div className="text-[12.5px] font-semibold text-[#1e293b] dark:text-[#e8e8e8] mb-1">{p.label}</div>
                      <div className="text-[11.5px] text-[#888] dark:text-[#666] mb-3 leading-relaxed">{p.desc}</div>
                      <div className="flex items-center justify-between">
                        {p.official ? (
                          <span className="flex items-center gap-1 text-[10.5px] text-[#3b82f6] font-medium">
                            <svg className="w-3 h-3" viewBox="0 0 16 16" fill="#3b82f6"><path d="M8 1l1.5 3 3.5.5-2.5 2.5.5 3.5L8 9l-3 1.5.5-3.5L3 4.5l3.5-.5z"/></svg>
                            官方
                          </span>
                        ) : <span />}
                        {isInstalled ? (
                          <span className="px-2.5 py-0.5 rounded-lg text-[10.5px] font-medium bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900">已安装</span>
                        ) : (
                          <button onClick={() => installPreset(p)} disabled={busy}
                            className="px-3 py-1 rounded-lg text-[11px] font-medium bg-[#1e293b] dark:bg-[#2a2a2a] text-white hover:opacity-80 transition-opacity disabled:opacity-40">
                            安装
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {error && <p className="text-[11.5px] text-red-500 mt-3">{error}</p>}
        </div>

        {/* Footer */}
        {mode !== "market" && (
          <div className="flex justify-end gap-2 px-6 py-4 border-t border-[#f0ede6] dark:border-[#222]">
            <button onClick={onClose} className="px-4 py-1.5 rounded-lg text-[12px] text-[#666] border border-[#e5e1d8] dark:border-[#252525] hover:bg-[#f5f2eb] dark:hover:bg-[#222] transition-colors">
              取消
            </button>
            <button onClick={submit} disabled={busy}
              className="px-4 py-1.5 rounded-lg text-[12px] bg-[#1e293b] dark:bg-[#2a2a2a] text-white hover:opacity-85 transition-opacity disabled:opacity-40">
              {busy ? "添加中…" : "添加 Server"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type DetailTab = "tools" | "config";

export default function CustomizeMcpPage() {
  const { data: servers = [], mutate } = useSWR<McpServer[]>("/api/mcp/", () => listServers());
  const [selected, setSelected] = useState<McpServer | null>(null);
  const [tab, setTab] = useState<DetailTab>("tools");
  const [showModal, setShowModal] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [discovering, setDiscovering] = useState(false);

  const refresh = async () => {
    const updated = await mutate();
    if (selected && updated) {
      const fresh = updated.find((s) => s.name === selected.name);
      setSelected(fresh ?? null);
    }
  };

  const discoverTools = async () => {
    setDiscovering(true);
    try {
      await reloadServers();
      await refresh();
    } catch (e) {
      console.error("Discover failed:", e);
    } finally {
      setDiscovering(false);
    }
  };

  const patch = async (body: McpServerPatch) => {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await patchServer(selected.name, body);
      setSelected(updated);
      mutate();
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!selected) return;
    if (!confirm(`删除 MCP Server "${selected.name}"？`)) return;
    setBusy(true);
    try {
      await deleteServer(selected.name);
      setSelected(null);
      mutate();
    } finally {
      setBusy(false);
      setMenuOpen(false);
    }
  };

  const patchTool = async (toolName: string, cfg: Partial<ToolConfig>) => {
    if (!selected) return;
    const current = selected.tools_config[toolName] ?? { approval: "confirm", enabled: true };
    const updated: Record<string, ToolConfig> = {
      ...selected.tools_config,
      [toolName]: { ...current, ...cfg },
    };
    await patch({ tools_config: updated });
  };

  const addTool = async () => {
    const name = prompt("工具名称（来自 MCP Server 的工具名）：");
    if (!name?.trim()) return;
    await patchTool(name.trim(), { approval: "confirm", enabled: true });
  };

  const filtered = q
    ? servers.filter((s) => s.name.toLowerCase().includes(q.toLowerCase()))
    : servers;

  const enabledServers = filtered.filter((s) => s.enabled);
  const disabledServers = filtered.filter((s) => !s.enabled);
  const installedNames = new Set(servers.map((s) => s.name));
  const toolEntries = Object.entries(selected?.tools_config ?? []);

  return (
    <div className="flex h-full overflow-hidden bg-[#f5f2eb] dark:bg-[#141414]">

      {/* ── Left: server list ── */}
      <div className="w-[280px] flex-shrink-0 flex flex-col border-r border-[#ddd9d0] dark:border-[#202020]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-5 pb-2">
          <h2 className="text-[14px] font-semibold text-[#1e293b] dark:text-[#e8e8e8]">MCP Servers</h2>
          <button onClick={() => setShowModal(true)}
            className="p-1.5 rounded-lg text-[#888] hover:text-[#333] dark:hover:text-[#ccc] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e] transition-colors" title="添加">
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 2v12M2 8h12"/></svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-4 pb-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a]">
            <svg className="w-3.5 h-3.5 text-[#bbb] flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="6.5" cy="6.5" r="4"/><path d="M11 11l2.5 2.5"/></svg>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索…"
              className="flex-1 bg-transparent text-[12px] text-[#1e293b] dark:text-[#c8c8c8] placeholder-[#bbb] focus:outline-none" />
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {servers.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2 text-[#bbb] dark:text-[#444]">
              <svg className="w-8 h-8 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              <span className="text-[12px]">还没有 MCP Server</span>
            </div>
          ) : (
            <>
              {enabledServers.length > 0 && (
                <>
                  <div className="px-3 py-1.5 text-[10px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wider">
                    已启用 · {enabledServers.length}
                  </div>
                  {enabledServers.map((s) => (
                    <ServerListItem key={s.name} server={s} active={selected?.name === s.name} onClick={() => { setSelected(s); setTab("tools"); }} />
                  ))}
                </>
              )}
              {disabledServers.length > 0 && (
                <>
                  <div className="px-3 py-1.5 mt-2 text-[10px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wider">
                    已停用
                  </div>
                  {disabledServers.map((s) => (
                    <ServerListItem key={s.name} server={s} active={selected?.name === s.name} onClick={() => { setSelected(s); setTab("tools"); }} />
                  ))}
                </>
              )}
            </>
          )}

          <button onClick={() => setShowModal(true)}
            className="w-full mt-3 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-dashed border-[#ccc8c0] dark:border-[#2a2a2a] text-[12px] text-[#aaa] dark:text-[#555] hover:border-[#1e90ff] hover:text-[#1e90ff] transition-colors">
            <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 2v12M2 8h12"/></svg>
            添加 MCP Server
          </button>
        </div>
      </div>

      {/* ── Right: detail ── */}
      {selected ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-start justify-between px-8 pt-6 pb-3 flex-shrink-0">
            <div>
              <h1 className="text-[18px] font-semibold text-[#1e293b] dark:text-[#e8e8e8] font-mono">{selected.name}</h1>
              <p className="text-[11.5px] text-[#aaa] dark:text-[#555] mt-0.5 font-mono">{selected.command ?? selected.url}</p>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              {/* Enable toggle */}
              <Toggle on={selected.enabled} disabled={busy}
                onToggle={() => patch({ enabled: !selected.enabled })} />
              {/* Three-dot menu */}
              <div className="relative">
                <button onClick={() => setMenuOpen((o) => !o)}
                  className="p-1.5 rounded-lg text-[#888] hover:text-[#333] dark:hover:text-[#ccc] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e] transition-colors">
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
                    <circle cx="8" cy="3" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="8" cy="13" r="1.2"/>
                  </svg>
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-8 w-36 rounded-xl border border-[#e5e1d8] dark:border-[#2a2a2a] bg-white dark:bg-[#1a1a1a] shadow-lg z-20 py-1 overflow-hidden">
                    <button onClick={() => { setMenuOpen(false); setTab("config"); }}
                      className="w-full text-left px-4 py-2 text-[12px] text-[#333] dark:text-[#ccc] hover:bg-[#f5f2eb] dark:hover:bg-[#222] transition-colors">
                      编辑配置
                    </button>
                    <div className="my-1 border-t border-[#f0ede6] dark:border-[#222]" />
                    <button onClick={remove} disabled={busy}
                      className="w-full text-left px-4 py-2 text-[12px] text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors disabled:opacity-30">
                      删除
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Meta row */}
          <div className="flex items-center gap-8 px-8 pb-4 flex-shrink-0">
            <div>
              <p className="text-[10px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">协议</p>
              <span className="px-2 py-0.5 rounded-md text-[11px] bg-[#e8e4dc] dark:bg-[#222] text-[#555] dark:text-[#888] font-mono">{selected.transport}</span>
            </div>
            <div>
              <p className="text-[10px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">状态</p>
              <span className={`flex items-center gap-1.5 text-[12px] font-medium ${selected.enabled ? "text-emerald-600 dark:text-emerald-400" : "text-[#aaa]"}`}>
                <StatusDot enabled={selected.enabled} />
                {selected.enabled ? "已启用" : "已停用"}
              </span>
            </div>
            <div>
              <p className="text-[10px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">工具</p>
              <p className="text-[12.5px] font-medium text-[#555] dark:text-[#aaa]">{toolEntries.length} 个</p>
            </div>
            {Object.keys(selected.env).length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">环境变量</p>
                <p className="text-[12.5px] font-medium text-[#555] dark:text-[#aaa]">{Object.keys(selected.env).length} 个</p>
              </div>
            )}
          </div>

          {/* Tabs */}
          <div className="flex gap-0 px-8 border-b border-[#ddd9d0] dark:border-[#202020] flex-shrink-0">
            {(["tools", "config"] as DetailTab[]).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-4 py-2.5 text-[12.5px] border-b-2 -mb-px transition-colors
                  ${tab === t ? "border-[#1e293b] dark:border-[#e8e8e8] text-[#1e293b] dark:text-[#e8e8e8] font-medium" : "border-transparent text-[#999] dark:text-[#555] hover:text-[#555] dark:hover:text-[#aaa]"}`}>
                {t === "tools" ? "工具列表" : "配置"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto">
            {/* Tools tab */}
            {tab === "tools" && (
              <div>
                <div className="flex items-center justify-between px-8 py-4">
                  <span className="text-[13px] font-semibold text-[#1e293b] dark:text-[#e8e8e8]">
                    工具 <span className="text-[#aaa] font-normal text-[11px] ml-1">{toolEntries.length} 个</span>
                  </span>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={discoverTools}
                      disabled={discovering}
                      className="flex items-center gap-1.5 text-[11.5px] text-[#1e90ff] hover:text-[#1070cc] transition-colors disabled:opacity-40"
                    >
                      <svg className={`w-3 h-3 ${discovering ? "animate-spin" : ""}`}
                        viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M13.5 8A5.5 5.5 0 112.5 8" strokeLinecap="round"/>
                        <path d="M13.5 4v4h-4"/>
                      </svg>
                      {discovering ? "发现中…" : "发现工具"}
                    </button>
                    <button onClick={addTool}
                      className="flex items-center gap-1.5 text-[11.5px] text-[#888] hover:text-[#333] dark:hover:text-[#ccc] transition-colors">
                      <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 2v12M2 8h12"/></svg>
                      添加工具
                    </button>
                  </div>
                </div>

                {toolEntries.length === 0 ? (
                  <div className="flex flex-col items-center py-16 text-[#bbb] dark:text-[#444] gap-2">
                    <svg className="w-10 h-10 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3-3a1 1 0 000-1.4l-1.6-1.6a1 1 0 00-1.4 0l-3 3zM13 8L8 13M5 20l3-3m0 0l-3-3m3 3h8"/></svg>
                    <p className="text-[12.5px]">暂无工具配置</p>
                    <p className="text-[11.5px]">点击「添加工具」手动输入工具名称</p>
                  </div>
                ) : (
                  toolEntries.map(([toolName, cfg]) => (
                    <div key={toolName}
                      className={`flex items-center gap-4 px-8 py-4 border-b border-[#f0ede6] dark:border-[#1e1e1e] transition-colors hover:bg-[#faf9f7] dark:hover:bg-[#161616] ${!cfg.enabled ? "opacity-50" : ""}`}>
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-[12.5px] font-semibold text-[#1e293b] dark:text-[#c8c8c8]">{toolName}</p>
                      </div>
                      <select
                        value={cfg.approval}
                        onChange={(e) => patchTool(toolName, { approval: e.target.value as ToolConfig["approval"] })}
                        className="px-2 py-1 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[11.5px] text-[#555] dark:text-[#aaa] outline-none cursor-pointer">
                        {Object.entries(APPROVAL_LABELS).map(([val, label]) => (
                          <option key={val} value={val}>{label}</option>
                        ))}
                      </select>
                      <Toggle on={cfg.enabled} onToggle={() => patchTool(toolName, { enabled: !cfg.enabled })} />
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Config tab */}
            {tab === "config" && (
              <div className="px-8 py-5 space-y-5">
                {/* Command / URL */}
                <div>
                  <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-2">
                    {selected.transport === "stdio" ? "启动命令" : "Server URL"}
                  </label>
                  <input defaultValue={selected.command ?? selected.url ?? ""}
                    onBlur={(e) => {
                      const val = e.target.value.trim();
                      if (val) patch(selected.transport === "stdio" ? { command: val } : { url: val });
                    }}
                    className="w-full px-3 py-2 rounded-xl border border-[#e5e1d8] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[12px] font-mono text-[#444] dark:text-[#aaa] outline-none focus:border-[#1e90ff]" />
                </div>

                {/* Env vars */}
                <div>
                  <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-2">环境变量</label>
                  <div className="space-y-2">
                    {Object.entries(selected.env).map(([k, v]) => (
                      <div key={k} className="flex gap-2 items-center">
                        <input readOnly value={k}
                          className="flex-1 px-3 py-1.5 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-[#f5f2eb] dark:bg-[#111] text-[11.5px] font-mono text-[#555] dark:text-[#888] outline-none" />
                        <input defaultValue={v} type="password"
                          onBlur={(e) => { patch({ env: { ...selected.env, [k]: e.target.value } }); }}
                          className="flex-[2] px-3 py-1.5 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[11.5px] font-mono text-[#444] dark:text-[#aaa] outline-none focus:border-[#1e90ff]" />
                        <button onClick={() => {
                          const env = { ...selected.env };
                          delete env[k];
                          patch({ env });
                        }} className="p-1.5 rounded-lg text-[#ccc] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors">
                          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 4h10M6 4V3h4v1M5 4l.5 9h5L11 4"/></svg>
                        </button>
                      </div>
                    ))}
                    {Object.keys(selected.env).length === 0 && (
                      <p className="text-[11.5px] text-[#bbb] dark:text-[#444] italic">无环境变量</p>
                    )}
                  </div>
                </div>

                {/* JSON preview */}
                <div>
                  <label className="block text-[11.5px] font-semibold text-[#666] dark:text-[#888] mb-2">JSON 配置（只读）</label>
                  <pre className="w-full px-4 py-3 rounded-xl border border-[#e5e1d8] dark:border-[#252525] bg-[#0e0e0e] text-[11.5px] font-mono text-[#aaa] leading-relaxed overflow-x-auto">
                    {buildJsonConfig(selected)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#ccc] dark:text-[#333] gap-3">
          <svg className="w-14 h-14 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          <p className="text-[13px]">从左侧选择一个 Server 查看详情</p>
          <button onClick={() => setShowModal(true)}
            className="mt-2 px-4 py-2 rounded-xl bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:opacity-85 transition-opacity">
            添加第一个 Server
          </button>
        </div>
      )}

      {menuOpen && <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />}

      {showModal && (
        <AddServerModal
          onClose={() => setShowModal(false)}
          onCreated={(s) => { setSelected(s); refresh(); }}
          installed={installedNames}
        />
      )}
    </div>
  );
}

// ── Server list item ──────────────────────────────────────────────────────────

function ServerListItem({ server, active, onClick }: { server: McpServer; active: boolean; onClick: () => void }) {
  const preset = PRESETS.find((p) => p.name === server.name);
  return (
    <div onClick={onClick}
      className={`flex items-center gap-2.5 pl-2 pr-3 py-2.5 rounded-xl cursor-pointer select-none transition-colors relative
        ${active ? "bg-[#eae7e0] dark:bg-[#222]" : "hover:bg-[#f0ede6] dark:hover:bg-[#181818]"}`}>
      {active && <div className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-[#1e90ff]" />}
      <div className="w-7 h-7 rounded-lg border border-[#e5e1d8] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] flex items-center justify-center text-sm flex-shrink-0">
        {preset?.icon ?? "🔌"}
      </div>
      <div className="flex-1 min-w-0">
        <p className={`font-mono text-[12px] font-semibold truncate ${!server.enabled ? "text-[#aaa] dark:text-[#555]" : "text-[#1e293b] dark:text-[#d0d0d0]"}`}>
          {server.name}
        </p>
        <p className="text-[10.5px] text-[#bbb] dark:text-[#444] mt-0.5">
          {Object.keys(server.tools_config).length} 个工具
        </p>
      </div>
      <StatusDot enabled={server.enabled} />
    </div>
  );
}
