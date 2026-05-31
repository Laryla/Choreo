// src/components/Sidebar/Sidebar.tsx
import { useState } from "react";
import useSWR from "swr";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { useTheme } from "@/hooks/useTheme";
import { THREADS_KEY } from "@/hooks/useChat";

import { apiFetch } from "@/lib/api";
const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

type NavItem = {
  to: string;
  label: string;
  icon: JSX.Element;
};

const NAV_ITEMS: NavItem[] = [
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
    to: "/customize",
    label: "自定义",
    icon: (
      <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="8" cy="8" r="2.5" />
        <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
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

  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem("sidebar-collapsed") === "true"
  );

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      localStorage.setItem("sidebar-collapsed", String(!prev));
      return !prev;
    });
  };

  return (
    <aside className={`flex-shrink-0 flex flex-col h-full bg-[#ebe7df] dark:bg-[#141414] border-r border-[#ddd9d0] dark:border-[#202020] transition-[width] duration-200 ease-in-out overflow-hidden ${collapsed ? "w-[44px]" : "w-[230px]"}`}>
      {/* Logo / Header */}
      {collapsed ? (
        <div className="flex items-center justify-center px-0 py-3 border-b border-[#ddd9d0] dark:border-[#202020]">
          <button
            onClick={toggleCollapsed}
            title="展开侧边栏"
            className="w-7 h-7 rounded flex items-center justify-center text-[13px] text-[#aaa] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8] transition-colors"
          >
            ›
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-base font-bold tracking-tight text-[#0f0f0f] dark:text-[#e8e8e8] whitespace-nowrap">
            Choreo
          </span>
          <button
            onClick={toggleCollapsed}
            title="收起侧边栏"
            className="w-6 h-6 rounded flex items-center justify-center text-[12px] text-[#aaa] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8] transition-colors"
          >
            ‹
          </button>
        </div>
      )}

      {/* New chat button */}
      <div className={`${collapsed ? "px-1.5 py-2 flex justify-center" : "px-2 mb-1"}`}>
        <button
          onClick={() => navigate("/chat")}
          title="新建对话"
          className={`flex items-center gap-2.5 rounded-lg text-[13px] cursor-pointer transition-colors text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8] ${
            collapsed ? "w-8 h-8 justify-center" : "w-full px-2.5 py-1.5"
          }`}
        >
          <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <line x1="8" y1="3" x2="8" y2="13" /><line x1="3" y1="8" x2="13" y2="8" />
          </svg>
          {!collapsed && <span>新建对话</span>}
        </button>
      </div>

      {/* Nav */}
      <nav className={`flex flex-col gap-0.5 ${collapsed ? "px-1.5 items-center" : "px-2"}`}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            title={item.label}
            className={({ isActive }) =>
              `flex items-center transition-colors rounded-lg cursor-pointer ${
                collapsed
                  ? `w-8 h-8 justify-center ${isActive ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8]" : "text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8]"}`
                  : `gap-2.5 px-2.5 py-1.5 text-[13px] ${isActive ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8] font-medium" : "text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8]"}`
              }`
            }
          >
            {item.icon}
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Recent threads */}
      {!collapsed && (
        <div className="mt-3 px-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-[#aaa] dark:text-[#444]">
          最近对话
        </div>
      )}
      {!collapsed && (
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
      )}
      {collapsed && <div className="flex-1" />}

      {/* Footer */}
      <div className={`border-t border-[#ddd9d0] dark:border-[#202020] flex items-center ${collapsed ? "justify-center py-2.5" : "gap-2 px-3 py-2.5"}`}>
        <div className="w-[30px] h-[30px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white dark:text-[#e8e8e8] text-xs font-bold flex-shrink-0">
          U
        </div>
        {!collapsed && (
          <>
            <div className="flex-1 min-w-0">
              <div className="text-[12px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] truncate">用户</div>
              <div className="text-[10px] text-[#999] dark:text-[#444]">deepseek-chat</div>
            </div>
            <div className="flex gap-0.5 bg-[#d6d0c7] dark:bg-[#1e1e1e] rounded-lg p-0.5">
              <button
                onClick={setLight}
                className={`px-2 py-1 rounded-md text-[10px] transition-colors ${theme === "light" ? "bg-[#f0ede6] shadow-sm text-[#0f0f0f]" : "text-[#555]"}`}
              >☀️</button>
              <button
                onClick={setDark}
                className={`px-2 py-1 rounded-md text-[10px] transition-colors ${theme === "dark" ? "bg-[#2e2e2e] text-[#e8e8e8]" : "text-[#aaa]"}`}
              >🌙</button>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
