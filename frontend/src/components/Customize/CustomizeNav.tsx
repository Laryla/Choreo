// frontend/src/components/Customize/CustomizeNav.tsx
import { NavLink } from "react-router-dom";

const ITEMS = [
  {
    to: "/customize/skills",
    label: "技能库",
    icon: (
      <svg className="w-4 h-4 flex-shrink-0 opacity-70" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M3 2h10v12H3z" />
        <line x1="5" y1="5" x2="11" y2="5" />
        <line x1="5" y1="8" x2="11" y2="8" />
        <line x1="5" y1="11" x2="8" y2="11" />
      </svg>
    ),
    comingSoon: false,
  },
  {
    to: "/customize/mcp",
    label: "MCP 连接器",
    icon: (
      <svg className="w-4 h-4 flex-shrink-0 opacity-70" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="5" cy="8" r="2" />
        <circle cx="11" cy="4" r="2" />
        <circle cx="11" cy="12" r="2" />
        <line x1="7" y1="7" x2="9" y2="5" />
        <line x1="7" y1="9" x2="9" y2="11" />
      </svg>
    ),
    comingSoon: true,
  },
  {
    to: "/customize/curator",
    label: "技能整理",
    icon: (
      <svg className="w-4 h-4 flex-shrink-0 opacity-70" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M8 2 L8 14" />
        <path d="M4 6 L8 2 L12 6" />
        <path d="M4 11 L8 7 L12 11" />
      </svg>
    ),
    comingSoon: false,
  },
];

export default function CustomizeNav() {
  return (
    <nav aria-label="自定义" className="w-[200px] flex-shrink-0 h-full bg-[#f0ede6] dark:bg-[#0f0f0f] border-r border-[#ddd9d0] dark:border-[#1a1a1a] flex flex-col pt-5 px-3">
      <div className="text-[10px] text-[#bbb] dark:text-[#3a3a3a] uppercase tracking-[0.08em] font-mono mb-3 px-2">
        自定义
      </div>
      <div className="flex flex-col gap-0.5">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[12.5px] cursor-pointer transition-colors ${
                isActive
                  ? "bg-[#e5e1d8] dark:bg-[#1c1c1c] text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                  : "text-[#666] dark:text-[#666] hover:bg-[#e8e4dc] dark:hover:bg-[#181818] hover:text-[#1a1a1a] dark:hover:text-[#ccc]"
              }`
            }
          >
            {item.icon}
            <span className="flex-1">{item.label}</span>
            {item.comingSoon && (
              <span className="text-[9px] text-[#aaa] dark:text-[#333] border border-[#ddd] dark:border-[#2a2a2a] rounded px-1 font-mono">
                即将推出
              </span>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
