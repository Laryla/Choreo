import { useState } from "react";
import { useChatStore } from "@/store/chatStore";
import { mutate } from "swr";
import { SKILLS_KEY } from "@/hooks/useChat";
import { apiFetch } from "@/lib/api";

interface Props {
  threadId: string;
}

export default function SkillSuggestionBanner({ threadId }: Props) {
  const { skillSuggestion, setSkillSuggestion } = useChatStore();
  const [saving, setSaving] = useState(false);

  if (!skillSuggestion) return null;

  const handleAccept = async () => {
    setSaving(true);
    try {
      const res = await apiFetch(`/threads/${threadId}/skill-suggestion/accept`, { method: "POST" });
      if (res.ok) {
        setSkillSuggestion(null);
        mutate(SKILLS_KEY);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDismiss = async () => {
    await apiFetch(`/threads/${threadId}/skill-suggestion/dismiss`, { method: "POST" });
    setSkillSuggestion(null);
  };

  return (
    <div className="mx-6 mb-3 px-4 py-3 rounded-xl border border-[#e6e2da] dark:border-[#2d2d48] bg-white dark:bg-[#1e1e35] flex items-start gap-3">
      <span className="text-base flex-shrink-0 mt-0.5">💡</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-[#1a1a1a] dark:text-[#e2e8f0] mb-0.5">
          建议保存为技能：{skillSuggestion.category}/{skillSuggestion.name}
        </p>
        <p className="text-xs text-[#888] dark:text-[#64748b] truncate">{skillSuggestion.description}</p>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        <button
          onClick={handleAccept}
          disabled={saving}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#6366f1] text-white hover:bg-[#5558e8] disabled:opacity-50 transition-colors"
        >
          {saving ? "保存中…" : "保存为技能"}
        </button>
        <button
          onClick={handleDismiss}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#f0ece3] dark:bg-[#22223a] text-[#555] dark:text-[#94a3b8] hover:opacity-80 transition-colors"
        >
          忽略
        </button>
      </div>
    </div>
  );
}
