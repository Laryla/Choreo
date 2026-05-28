// src/components/Topbar/Topbar.tsx
import { ReactNode } from "react";

interface TopbarProps {
  title: string;
  action?: ReactNode;
}

export default function Topbar({ title, action }: TopbarProps) {
  return (
    <div className="flex items-center justify-between px-5 py-2.5 border-b border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
      <span className="text-[13px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">
        {title}
      </span>
      {action ?? (
        <div className="flex items-center gap-1.5 bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555] dark:text-[#777] text-[11px] px-2.5 py-1 rounded-lg cursor-pointer">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
          deepseek-chat ▾
        </div>
      )}
    </div>
  );
}
