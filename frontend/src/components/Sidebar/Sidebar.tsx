// src/components/Sidebar/Sidebar.tsx
import useSWR from "swr";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { useTheme } from "@/hooks/useTheme";
import { THREADS_KEY } from "@/hooks/useChat";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const fetcher = (url: string) => fetch(`${API}${url}`).then((r) => r.json());

const NAV_ITEMS = [
  {
    to: "/tasks",
    label: "定时任务",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <rect x="2" y="3" width="12" height="10" rx="1.5" />
        <line x1="5" y1="7" x2="11" y2="7" /><line x1="5" y1="10" x2="8" y2="10" />
      </svg>
    ),
  },
  {
    to: "/history",
    label: "历史记录",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="8" cy="8" r="5.5" /><polyline points="8 5 8 8 10 10" />
      </svg>
    ),
  },
  {
    to: "/skills",
    label: "技能库",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M3 2h10v12H3z" />
        <line x1="5" y1="5" x2="11" y2="5" />
        <line x1="5" y1="8" x2="11" y2="8" />
        <line x1="5" y1="11" x2="8" y2="11" />
      </svg>
    ),
  },
];

export default function Sidebar() {
  const { theme, setLight, setDark } = useTheme();
  const navigate = useNavigate();
  const { threadId: activeThreadId } = useParams<{ threadId?: string }>();
  const { data: threads = [] } = useSWR<{ thread_id: string; status: string; title?: string }[]>(
    THREADS_KEY,
    fetcher,
    { revalidateOnFocus: true, onErrorRetry: () => {} },
  );

  return (
    <aside className="w-[230px] flex-shrink-0 flex flex-col h-full bg-[#ebe7df] dark:bg-[#141414] border-r border-[#ddd9d0] dark:border-[#202020]">
      {/* Logo */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-base font-bold tracking-tight text-[#0f0f0f] dark:text-[#e8e8e8]">
          Choreo
        </span>
        <button className="w-6 h-6 rounded flex items-center justify-center text-xs opacity-40 hover:opacity-70">
          ⊡
        </button>
      </div>

      {/* New chat button */}
      <div className="px-2 mb-1">
        <button
          onClick={() => navigate("/chat")}
          className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8]"
        >
          <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <line x1="8" y1="3" x2="8" y2="13" /><line x1="3" y1="8" x2="13" y2="8" />
          </svg>
          新建对话
        </button>
      </div>

      {/* Nav */}
      <nav className="px-2 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors ${
                isActive
                  ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                  : "text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8]"
              }`
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Recent threads */}
      <div className="mt-3 px-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-[#aaa] dark:text-[#444]">
        最近对话
      </div>
      <div className="flex-1 overflow-y-auto flex flex-col">
        {threads.length === 0 ? (
          <p className="px-4 py-2 text-[11px] text-[#bbb] dark:text-[#333]">暂无对话</p>
        ) : (
          threads.slice(0, 20).map((t) => (
            <button
              key={t.thread_id}
              onClick={() => navigate(`/chat/${t.thread_id}`)}
              className={`text-left px-4 py-1.5 text-[12px] truncate flex items-center gap-2 transition-colors ${
                activeThreadId === t.thread_id
                  ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8]"
                  : "text-[#666] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8]"
              }`}
            >
              <span className="truncate">{t.title ?? `对话 ${t.thread_id.slice(0, 8)}`}</span>
              {t.status === "interrupted" && (
                <span className="text-[9px] text-amber-500 flex-shrink-0">●</span>
              )}
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2.5 border-t border-[#ddd9d0] dark:border-[#202020] flex items-center gap-2">
        <div className="w-[30px] h-[30px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white dark:text-[#e8e8e8] text-xs font-bold flex-shrink-0">
          U
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] truncate">用户</div>
          <div className="text-[10px] text-[#999] dark:text-[#444]">deepseek-chat</div>
        </div>
        {/* Theme toggle */}
        <div className="flex gap-0.5 bg-[#d6d0c7] dark:bg-[#1e1e1e] rounded-lg p-0.5">
          <button
            onClick={setLight}
            className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
              theme === "light"
                ? "bg-[#f0ede6] shadow-sm text-[#0f0f0f]"
                : "text-[#555]"
            }`}
          >☀️</button>
          <button
            onClick={setDark}
            className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
              theme === "dark"
                ? "bg-[#2e2e2e] text-[#e8e8e8]"
                : "text-[#aaa]"
            }`}
          >🌙</button>
        </div>
      </div>
    </aside>
  );
}
