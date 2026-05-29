import { useCallback, useEffect, useRef, useState } from "react";
import { mutate } from "swr";
import { client } from "@/lib/client";
import { useChatStore } from "@/store/chatStore";
import { useReviewStore } from "@/store/reviewStore";

export const THREADS_KEY = "/threads/";

export function useChat(initialThreadId?: string) {
  const threadIdRef = useRef<string | null>(initialThreadId ?? null);
  const [streaming, setStreaming] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(initialThreadId ?? null);

  // 路由切换时同步重置 ref，避免新建聊天时还用旧 thread ID
  useEffect(() => {
    threadIdRef.current = initialThreadId ?? null;
    setCurrentThreadId(initialThreadId ?? null);
  }, [initialThreadId]);
  const { addMessage, appendToken, appendThinking, finalizeToken } = useChatStore();
  const { openReview } = useReviewStore();

  async function ensureThread(): Promise<string> {
    if (threadIdRef.current) return threadIdRef.current;
    const thread = await client.threads.create();
    threadIdRef.current = thread.thread_id;
    setCurrentThreadId(thread.thread_id);
    mutate(THREADS_KEY);
    return thread.thread_id;
  }

  const sendMessage = useCallback(async (text: string, context?: Record<string, unknown>) => {
    addMessage({ role: "user", content: text });
    setStreaming(true);

    try {
      const tid = await ensureThread();
      const stream = client.runs.stream(tid, "choreo", {
        input: { messages: [{ role: "user", content: text }] },
        streamMode: ["messages", "updates"],
        ...(context && Object.keys(context).length > 0 ? { context } : {}),
      } as any);

      for await (const chunk of stream as any) {
        if (chunk.event === "messages") {
          const msgs: any[] = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs) {
            if (!msg) continue;

            // DeepSeek reasoner: additional_kwargs.reasoning_content
            const reasoning = msg.additional_kwargs?.reasoning_content;
            if (reasoning) appendThinking(reasoning);

            const content = msg.content;
            if (typeof content === "string") {
              if (content) appendToken(content);
            } else if (Array.isArray(content)) {
              // Claude thinking blocks: [{type: "thinking", thinking: "..."}, {type: "text", text: "..."}]
              for (const block of content) {
                if (block.type === "thinking" || block.type === "reasoning") {
                  const t = block.thinking ?? block.reasoning ?? "";
                  if (t) appendThinking(t);
                } else if (block.type === "text" && block.text) {
                  appendToken(block.text);
                }
              }
            }
          }
        }
        if (chunk.event === "updates" && chunk.data?.__interrupt__) {
          const interruptValue = chunk.data.__interrupt__[0]?.value;
          if (interruptValue?.action_requests) {
            openReview({ threadId: tid, ...interruptValue });
          }
          break;
        }
      }
    } finally {
      finalizeToken();
      setStreaming(false);
      mutate(THREADS_KEY);
    }
  }, []);

  return { sendMessage, streaming, threadId: currentThreadId };
}
