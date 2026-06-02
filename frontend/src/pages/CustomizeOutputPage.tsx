import { useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { listOutputFiles, getFileUrl, type OutputFile } from "@/api/output";
import { THREADS_KEY } from "@/hooks/useChat";
import FileBrowser from "@/components/Output/FileBrowser";
import FilePreview from "@/components/Output/FilePreview";

type Thread = { thread_id: string; status: string; title?: string };

const threadFetcher = (url: string) => apiFetch(url).then((r) => r.json());

export default function CustomizeOutputPage() {
  const [selectedThread, setSelectedThread] = useState("");
  const [subdir, setSubdir] = useState("");
  const [breadcrumb, setBreadcrumb] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<OutputFile | null>(null);

  const { data: threads = [] } = useSWR<Thread[]>(THREADS_KEY, threadFetcher, {
    revalidateOnFocus: true,
  });

  const { data, isLoading, error } = useSWR(
    ["output", selectedThread, subdir],
    () => listOutputFiles(subdir, selectedThread),
  );

  const handleThreadChange = (tid: string) => {
    setSelectedThread(tid);
    setSubdir("");
    setBreadcrumb([]);
    setSelectedFile(null);
  };

  const enterDir = (name: string) => {
    const next = subdir ? `${subdir}/${name}` : name;
    setSubdir(next);
    setBreadcrumb([...breadcrumb, name]);
    setSelectedFile(null);
  };

  const goTo = (idx: number) => {
    const crumbs = breadcrumb.slice(0, idx + 1);
    setBreadcrumb(crumbs);
    setSubdir(crumbs.join("/"));
    setSelectedFile(null);
  };

  const goRoot = () => {
    setBreadcrumb([]);
    setSubdir("");
    setSelectedFile(null);
  };

  const download = (file: OutputFile) => {
    const path = subdir ? `${subdir}/${file.name}` : file.name;
    window.open(getFileUrl(path, selectedThread));
  };

  const downloadSelected = () => {
    if (selectedFile) download(selectedFile);
  };

  return (
    <div className="flex h-full overflow-hidden bg-[#faf9f7] dark:bg-[#0a0a0a]">
      {/* Left: file browser (40%) */}
      <div className="w-[40%] min-w-[200px] max-w-[320px] flex-shrink-0 bg-white dark:bg-[#0d0d0d]">
        <FileBrowser
          threads={threads}
          selectedThread={selectedThread}
          breadcrumb={breadcrumb}
          files={data?.files ?? []}
          isLoading={isLoading}
          error={error}
          selectedFile={selectedFile}
          onThreadChange={handleThreadChange}
          onGoRoot={goRoot}
          onGoTo={goTo}
          onEnterDir={enterDir}
          onSelectFile={setSelectedFile}
          onDownload={download}
        />
      </div>

      {/* Right: preview (60%) */}
      <div className="flex-1 min-w-0 bg-white dark:bg-[#0d0d0d]">
        <FilePreview
          file={selectedFile}
          subdir={subdir}
          threadId={selectedThread}
          onDownload={downloadSelected}
        />
      </div>
    </div>
  );
}
