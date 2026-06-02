import { type OutputFile } from "@/api/output";

type Thread = { thread_id: string; status: string; title?: string };

interface FileBrowserProps {
  threads: Thread[];
  selectedThread: string;
  breadcrumb: string[];
  files: OutputFile[];
  isLoading: boolean;
  error: unknown;
  selectedFile: OutputFile | null;
  onThreadChange: (tid: string) => void;
  onGoRoot: () => void;
  onGoTo: (idx: number) => void;
  onEnterDir: (name: string) => void;
  onSelectFile: (file: OutputFile) => void;
  onDownload: (file: OutputFile) => void;
}

export default function FileBrowser({
  threads,
  selectedThread,
  breadcrumb,
  files,
  isLoading,
  error,
  selectedFile,
  onThreadChange,
  onGoRoot,
  onGoTo,
  onEnterDir,
  onSelectFile,
  onDownload,
}: FileBrowserProps) {
  const selectedTitle =
    threads.find((t) => t.thread_id === selectedThread)?.title ||
    (selectedThread ? selectedThread.slice(0, 8) + "…" : "");

  return (
    <div className="flex flex-col h-full border-r border-[#e8e4dc] dark:border-[#1a1a1a] overflow-hidden">
      {/* Thread selector */}
      <div className="flex-shrink-0 px-4 pt-4 pb-3 border-b border-[#e8e4dc] dark:border-[#1a1a1a]">
        <label className="block text-[10px] text-[#aaa] dark:text-[#555] font-medium uppercase tracking-wide mb-1.5">
          对话
        </label>
        <select
          value={selectedThread}
          onChange={(e) => onThreadChange(e.target.value)}
          className="w-full text-[12px] px-2.5 py-1.5 rounded-lg border border-[#e8e4dc] dark:border-[#1a1a1a] bg-white dark:bg-[#0d0d0d] text-[#333] dark:text-[#ccc] focus:outline-none focus:ring-1 focus:ring-[#c8b89a]"
        >
          <option value="">— 全部线程 —</option>
          {threads.map((t) => (
            <option key={t.thread_id} value={t.thread_id}>
              {t.title || t.thread_id.slice(0, 8) + "…"}
            </option>
          ))}
        </select>
      </div>

      {/* Breadcrumb */}
      <div className="flex-shrink-0 flex items-center gap-1 px-4 py-2 text-[11px] text-[#aaa] dark:text-[#555] font-mono border-b border-[#e8e4dc] dark:border-[#1a1a1a]">
        <button
          onClick={onGoRoot}
          className="hover:text-[#555] dark:hover:text-[#aaa] transition-colors"
        >
          {selectedTitle ? `${selectedTitle}/` : "output/"}
        </button>
        {breadcrumb.map((seg, i) => (
          <span key={i} className="flex items-center gap-1">
            <span>/</span>
            <button
              onClick={() => onGoTo(i)}
              className="hover:text-[#555] dark:hover:text-[#aaa] transition-colors"
            >
              {seg}
            </button>
          </span>
        ))}
      </div>

      {/* File list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="px-4 py-8 text-center text-[12px] text-[#bbb] dark:text-[#333]">
            加载中…
          </div>
        )}
        {!isLoading && error != null && (
          <div className="px-4 py-8 text-center text-[12px] text-[#e07b54]">
            Sandbox 未运行，请先发送消息
          </div>
        )}
        {!isLoading && !error && files.length === 0 && (
          <div className="px-4 py-8 text-center text-[12px] text-[#bbb] dark:text-[#333]">
            output/ 目录为空
          </div>
        )}
        {!isLoading && !error && files.length > 0 && (
          <table className="w-full text-[12px]">
            <tbody>
              {files.map((f) => {
                const isSelected =
                  f.type === "file" && selectedFile?.name === f.name;
                return (
                  <tr
                    key={f.name}
                    className={`border-b border-[#f0ede6] dark:border-[#141414] last:border-0 transition-colors ${
                      isSelected
                        ? "bg-[#f0ede6] dark:bg-[#181818]"
                        : "hover:bg-[#faf8f5] dark:hover:bg-[#111]"
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      {f.type === "dir" ? (
                        <button
                          onClick={() => onEnterDir(f.name)}
                          className="flex items-center gap-2 text-[#569cd6] hover:underline w-full text-left"
                        >
                          <svg
                            className="w-3.5 h-3.5 opacity-60 flex-shrink-0"
                            viewBox="0 0 16 16"
                            fill="currentColor"
                          >
                            <path d="M1.5 3.5A1.5 1.5 0 013 2h3.586a1.5 1.5 0 011.06.44L8.707 3.5H13A1.5 1.5 0 0114.5 5v7A1.5 1.5 0 0113 13.5H3A1.5 1.5 0 011.5 12V3.5z" />
                          </svg>
                          <span className="truncate">{f.name}/</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => onSelectFile(f)}
                          className="flex items-center gap-2 w-full text-left"
                        >
                          <svg
                            className="w-3.5 h-3.5 opacity-40 flex-shrink-0"
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.5"
                          >
                            <path d="M4 1.5h5.5L12.5 4.5V14.5H4V1.5z" />
                            <polyline points="9.5 1.5 9.5 4.5 12.5 4.5" />
                          </svg>
                          <span
                            className={`truncate ${
                              isSelected
                                ? "text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                                : "text-[#333] dark:text-[#ccc]"
                            }`}
                          >
                            {f.name}
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-[#aaa] dark:text-[#555] font-mono text-[11px] whitespace-nowrap">
                      {f.size !== null ? formatSize(f.size) : ""}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {f.type === "file" && (
                        <button
                          onClick={() => onDownload(f)}
                          className="text-[11px] text-[#aaa] dark:text-[#444] hover:text-[#333] dark:hover:text-[#aaa] transition-colors"
                          title="下载"
                        >
                          ↓
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
