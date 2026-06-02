import useSWR from "swr";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getFileUrl, getRawUrl, type OutputFile } from "@/api/output";

type FileType = "image" | "markdown" | "text";

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"]);
const MARKDOWN_EXTS = new Set(["md", "mdx", "markdown"]);

function getFileType(name: string): FileType {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (IMAGE_EXTS.has(ext)) return "image";
  if (MARKDOWN_EXTS.has(ext)) return "markdown";
  return "text";
}

async function fetchText(url: string): Promise<string> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.text();
}

interface FilePreviewProps {
  file: OutputFile | null;
  subdir: string;
  threadId: string;
  onDownload: () => void;
}

export default function FilePreview({
  file,
  subdir,
  threadId,
  onDownload,
}: FilePreviewProps) {
  if (!file) {
    return (
      <div className="flex items-center justify-center h-full text-[12px] text-[#bbb] dark:text-[#333]">
        ← 点击左侧文件预览
      </div>
    );
  }

  const filePath = subdir ? `${subdir}/${file.name}` : file.name;
  const fileType = getFileType(file.name);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-[#e8e4dc] dark:border-[#1a1a1a] bg-white dark:bg-[#0d0d0d]">
        <span className="text-[12px] font-mono text-[#555] dark:text-[#aaa] truncate" title={file.name}>
          {file.name}
        </span>
        <button
          onClick={onDownload}
          className="flex-shrink-0 ml-3 text-[11px] text-[#888] dark:text-[#555] hover:text-[#333] dark:hover:text-[#aaa] transition-colors border border-[#e0dbd2] dark:border-[#222] rounded px-2 py-0.5"
        >
          ↓ 下载
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-auto bg-white dark:bg-[#0d0d0d]">
        {fileType === "image" ? (
          <ImagePreview
            src={getRawUrl(filePath, threadId)}
            name={file.name}
          />
        ) : (
          <TextPreview
            filePath={filePath}
            threadId={threadId}
            fileType={fileType}
          />
        )}
      </div>
    </div>
  );
}

function ImagePreview({ src, name }: { src: string; name: string }) {
  return (
    <div className="flex items-center justify-center p-6 min-h-full">
      <img
        src={src}
        alt={name}
        className="max-w-full max-h-[70vh] object-contain rounded shadow"
        onError={(e) => {
          const img = e.target as HTMLImageElement;
          img.style.display = "none";
          const msg = document.createElement("p");
          msg.textContent = "图片加载失败";
          msg.className = "text-[12px] text-[#e07b54]";
          img.parentElement?.appendChild(msg);
        }}
      />
    </div>
  );
}

function TextPreview({
  filePath,
  threadId,
  fileType,
}: {
  filePath: string;
  threadId: string;
  fileType: "markdown" | "text";
}) {
  const url = getFileUrl(filePath, threadId);
  const { data: content, isLoading, error } = useSWR(
    ["preview", filePath, threadId],
    () => fetchText(url),
  );

  if (isLoading) {
    return (
      <div className="px-6 py-8 text-center text-[12px] text-[#bbb] dark:text-[#333]">
        加载中…
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-6 py-8 text-center text-[12px] text-[#e07b54]">
        加载失败：{String((error as Error)?.message ?? error)}
      </div>
    );
  }

  if (fileType === "markdown") {
    return (
      <div className="px-6 py-5 prose prose-sm dark:prose-invert max-w-none text-[13px] leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content ?? ""}
        </ReactMarkdown>
      </div>
    );
  }

  // Plain text / code with line numbers
  const lines = (content ?? "").split("\n");
  return (
    <div className="overflow-x-auto">
      <table className="text-[11.5px] font-mono leading-[1.65] w-full border-collapse">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className="hover:bg-[#f8f6f2] dark:hover:bg-[#111]">
              <td className="pl-4 pr-3 text-right text-[#ccc] dark:text-[#333] select-none w-[3rem] border-r border-[#ece8e0] dark:border-[#1a1a1a]">
                {i + 1}
              </td>
              <td className="pl-4 pr-6 text-[#333] dark:text-[#ccc] whitespace-pre">
                {line}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
