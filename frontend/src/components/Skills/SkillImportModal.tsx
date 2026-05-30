import { useState } from "react";
import {
  previewImport,
  confirmImport,
  type PreviewSkill,
} from "@/api/skills";

type Step = "category" | "select" | "conflict" | "done";

interface Props {
  file: File;
  onClose: () => void;
  onDone: () => void;
}

export default function SkillImportModal({ file, onClose, onDone }: Props) {
  const isZip = file.name.endsWith(".zip");

  const [step, setStep] = useState<Step>(isZip ? "select" : "category");
  const [category, setCategory] = useState("imported");
  const [sessionId, setSessionId] = useState("");
  const [skills, setSkills] = useState<PreviewSkill[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [decisions, setDecisions] = useState<Record<string, "overwrite" | "skip">>({});
  const [importedCount, setImportedCount] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const skillId = (s: PreviewSkill) => `${s.category}/${s.name}`;

  const runPreview = async (cat?: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await previewImport(file, cat ?? category);
      setSessionId(res.session_id);
      setSkills(res.skills);
      const allIds = new Set(res.skills.map(skillId));
      setChecked(allIds);
      if (isZip) {
        setStep("select");
      } else {
        const conflict = res.skills.some((s) => s.conflict);
        conflict ? setStep("conflict") : await runConfirm(res.session_id, res.skills, {}, allIds);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const runConfirm = async (
    sid: string,
    allSkills: PreviewSkill[],
    dec: Record<string, "overwrite" | "skip">,
    checkedIds: Set<string>
  ) => {
    setLoading(true);
    setError("");
    try {
      const selections = [...checkedIds].filter((id) =>
        allSkills.some((s) => skillId(s) === id)
      );
      const res = await confirmImport({ session_id: sid, selections, conflict_decisions: dec });
      setImportedCount(res.imported.length);
      setStep("done");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleCheck = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const setAllDecisions = (val: "overwrite" | "skip") => {
    const dec: Record<string, "overwrite" | "skip"> = {};
    skills.filter((s) => s.conflict && checked.has(skillId(s))).forEach((s) => {
      dec[skillId(s)] = val;
    });
    setDecisions(dec);
  };

  const conflictSkills = skills.filter((s) => s.conflict && checked.has(skillId(s)));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white dark:bg-[#1a1a1a] border border-[#ddd9d0] dark:border-[#252525] rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[#eee] dark:border-[#252525] flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">导入技能</h2>
          <button onClick={onClose} className="text-[#aaa] hover:text-[#555] text-lg leading-none">×</button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {error && (
            <div className="mb-3 text-[12px] text-red-500 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          {/* Step: category (single .md only) */}
          {step === "category" && (
            <div>
              <p className="text-[12px] text-[#555] dark:text-[#888] mb-3">
                文件：<span className="font-mono">{file.name}</span>
              </p>
              <label className="block text-[11px] font-semibold text-[#666] dark:text-[#999] mb-1.5 uppercase tracking-wide">
                分类 (Category)
              </label>
              <input
                className="w-full px-3 py-2 rounded-lg border border-[#ddd] dark:border-[#333] bg-white dark:bg-[#111] text-[13px] text-[#1a1a1a] dark:text-[#ccc] focus:outline-none focus:ring-1 focus:ring-[#1e293b]"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="imported"
              />
              <p className="text-[11px] text-[#aaa] mt-1.5">用于组织技能的目录名，如 design / animation</p>
            </div>
          )}

          {/* Step: select (zip) */}
          {step === "select" && skills.length === 0 && (
            <p className="text-[12px] text-[#888]">点击「解析文件」开始解析 zip 包中的技能</p>
          )}
          {step === "select" && skills.length > 0 && (
            <div>
              <p className="text-[12px] text-[#555] dark:text-[#888] mb-3">
                共找到 {skills.length} 个技能，勾选要导入的：
              </p>
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {skills.map((s) => (
                  <label key={skillId(s)} className="flex items-center gap-2.5 px-3 py-2 rounded-lg border border-[#eee] dark:border-[#252525] bg-[#fafafa] dark:bg-[#111] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked.has(skillId(s))}
                      onChange={() => toggleCheck(skillId(s))}
                      className="accent-[#1e293b]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] font-semibold text-[#1a1a1a] dark:text-[#ddd] truncate">{s.name}</div>
                      <div className="text-[10px] text-[#aaa] font-mono">{s.category}/</div>
                    </div>
                    {s.conflict && (
                      <span className="text-[9px] bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 px-1.5 py-0.5 rounded font-medium">已存在</span>
                    )}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Step: conflict */}
          {step === "conflict" && (
            <div>
              <p className="text-[12px] text-[#555] dark:text-[#888] mb-2">
                以下技能已存在，请选择处理方式：
              </p>
              <div className="flex gap-2 mb-3">
                <button onClick={() => setAllDecisions("overwrite")} className="flex-1 py-1.5 text-[11px] rounded-lg border border-[#ddd] dark:border-[#333] hover:bg-[#f5f5f5] dark:hover:bg-[#222] text-[#555] dark:text-[#999]">全部覆盖</button>
                <button onClick={() => setAllDecisions("skip")} className="flex-1 py-1.5 text-[11px] rounded-lg border border-[#ddd] dark:border-[#333] hover:bg-[#f5f5f5] dark:hover:bg-[#222] text-[#555] dark:text-[#999]">全部跳过</button>
              </div>
              <div className="space-y-2 max-h-52 overflow-y-auto">
                {conflictSkills.map((s) => {
                  const id = skillId(s);
                  const dec = decisions[id] ?? "overwrite";
                  return (
                    <div key={id} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-900/10">
                      <div className="flex-1 text-[12px] font-medium text-[#555] dark:text-[#999] truncate">{id}</div>
                      <button
                        onClick={() => setDecisions((d) => ({ ...d, [id]: "overwrite" }))}
                        className={`px-2.5 py-1 rounded text-[11px] ${dec === "overwrite" ? "bg-[#1e293b] text-white" : "bg-white dark:bg-[#222] border border-[#ddd] dark:border-[#333] text-[#666]"}`}
                      >覆盖</button>
                      <button
                        onClick={() => setDecisions((d) => ({ ...d, [id]: "skip" }))}
                        className={`px-2.5 py-1 rounded text-[11px] ${dec === "skip" ? "bg-[#1e293b] text-white" : "bg-white dark:bg-[#222] border border-[#ddd] dark:border-[#333] text-[#666]"}`}
                      >跳过</button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Step: done */}
          {step === "done" && (
            <div className="text-center py-4">
              <div className="text-3xl mb-2">✅</div>
              <p className="text-[14px] font-semibold text-[#1a1a1a] dark:text-[#e8e8e8]">导入成功</p>
              <p className="text-[12px] text-[#888] mt-1">已导入 {importedCount} 个技能</p>
            </div>
          )}
        </div>

        {/* Footer */}
        {step !== "done" && (
          <div className="px-5 py-3 border-t border-[#eee] dark:border-[#252525] flex justify-end gap-2">
            <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-[12px] text-[#666] hover:bg-[#f5f5f5] dark:hover:bg-[#222]">取消</button>

            {step === "category" && (
              <button
                disabled={loading || !category.trim()}
                onClick={() => runPreview(category)}
                className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
              >{loading ? "解析中…" : "下一步"}</button>
            )}

            {step === "select" && (
              <>
                {skills.length === 0 && (
                  <button
                    disabled={loading}
                    onClick={() => runPreview()}
                    className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
                  >{loading ? "解析中…" : "解析文件"}</button>
                )}
                {skills.length > 0 && (
                  <button
                    disabled={loading || checked.size === 0}
                    onClick={() => {
                      const hasConflict = skills.some((s) => s.conflict && checked.has(skillId(s)));
                      hasConflict ? setStep("conflict") : runConfirm(sessionId, skills, {}, checked);
                    }}
                    className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
                  >{loading ? "导入中…" : "下一步"}</button>
                )}
              </>
            )}

            {step === "conflict" && (
              <button
                disabled={loading}
                onClick={() => runConfirm(sessionId, skills, decisions, checked)}
                className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
              >{loading ? "导入中…" : "确认导入"}</button>
            )}
          </div>
        )}
        {step === "done" && (
          <div className="px-5 py-3 border-t border-[#eee] dark:border-[#252525] flex justify-end">
            <button onClick={() => { onDone(); onClose(); }} className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px]">关闭</button>
          </div>
        )}
      </div>
    </div>
  );
}
