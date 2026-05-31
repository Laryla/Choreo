// src/components/Topbar/Topbar.tsx
import { ReactNode } from "react";
import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "@/lib/api";
import { authStore } from "@/store/authStore";

interface TopbarProps {
  title: string;
  action?: ReactNode;
}

function UserChip() {
  const navigate = useNavigate();
  const { data: me } = useSWR(
    authStore.isAuthenticated() ? "/auth/me" : null,
    (url) => apiFetch(url).then((r) => r.json()),
    { revalidateOnFocus: false }
  );

  const logout = () => {
    authStore.clearTokens();
    navigate("/login", { replace: true });
  };

  if (!me) return null;

  return (
    <div className="flex items-center gap-2 ml-2">
      {me.avatar && (
        <img src={me.avatar} alt="" className="w-6 h-6 rounded-full flex-shrink-0" />
      )}
      <span className="text-[11.5px] text-[#888] dark:text-[#666] max-w-[80px] truncate">
        {me.name}
      </span>
      <button
        onClick={logout}
        className="text-[11px] text-[#aaa] hover:text-[#555] dark:hover:text-[#ccc] transition-colors flex-shrink-0"
      >
        退出
      </button>
    </div>
  );
}

export default function Topbar({ title, action }: TopbarProps) {
  return (
    <div className="flex items-center justify-between px-5 py-2.5 border-b border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
      <span className="text-[13px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">
        {title}
      </span>
      <div className="flex items-center gap-2">
        {action ?? (
          <div className="flex items-center gap-1.5 bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555] dark:text-[#777] text-[11px] px-2.5 py-1 rounded-lg cursor-pointer">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
            deepseek-chat ▾
          </div>
        )}
        <UserChip />
      </div>
    </div>
  );
}
