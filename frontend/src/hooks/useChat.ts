import { useCallback, useRef, useState } from "react";
import { client } from "@/lib/client";
import { useChatStore } from "@/store/chatStore";
import { useReviewStore } from "@/store/reviewStore";

export function useChat() {
  const threadIdRef = useRef<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const { addMessage, appendToken, appendThinking, finalizeToken } = useChatStore();
  const { openReview } = useReviewStore();

  async function ensureThread(): Promise<string> {
    if (threadIdRef.current) return threadIdRef.current;
    const thread = await client.threads.create();
    threadIdRef.current = thread.thread_id;
    return thread.thread_id;
  }

  const sendMessage = useCallback(async (text: string) => {
    addMessage({ role: "user", content: text });
    setStreaming(true);

    try {
      const tid = await ensureThread();
      const stream = client.runs.stream(tid, "choreo", {
        input: { messages: [{ role: "user", content: text }] },
        streamMode: ["messages", "updates"],
      });

      for await (const chunk of stream as any) {
        if (chunk.event === "thinking") {
          if (chunk.data?.content) appendThinking(chunk.data.content);
        }
        if (chunk.event === "messages") {
          const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs) {
            if (msg?.content) appendToken(typeof msg.content === "string" ? msg.content : "");
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
    }
  }, []);

  return { sendMessage, streaming, threadId: threadIdRef.current };
}
