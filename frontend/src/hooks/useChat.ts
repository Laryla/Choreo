import { useCallback, useEffect, useRef, useState } from "react";
import { mutate } from "swr";
import { client } from "@/lib/client";
import { useChatStore } from "@/store/chatStore";
import { useReviewStore } from "@/store/reviewStore";

export const THREADS_KEY = "/threads/";
export const SKILLS_KEY = "/api/skills/?";

export function useChat(initialThreadId?: string) {
  const threadIdRef = useRef<string | null>(initialThreadId ?? null);
  const [streaming, setStreaming] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(initialThreadId ?? null);

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
        streamMode: ["messages", "updates", "custom", "tasks", "values"],
        ...(context && Object.keys(context).length > 0 ? { context } : {}),
      } as any);

      let reviewStarted = false;

      for await (const chunk of stream as any) {
        // ── LLM token 流 ─────────────────────────────────────────
        if (chunk.event === "messages") {
          const msgs: any[] = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs) {
            if (!msg) continue;

            const reasoning = msg.additional_kwargs?.reasoning_content;
            if (reasoning) appendThinking(reasoning);

            const content = msg.content;
            if (typeof content === "string") {
              if (content) appendToken(content);
            } else if (Array.isArray(content)) {
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

        // ── 节点状态更新 ─────────────────────────────────────────
        if (chunk.event === "updates") {
          const data = chunk.data ?? {};

          // Skill review signal — consume and skip
          if (data.__review_started__ !== undefined) {
            if (data.__review_started__ === true) reviewStarted = true;
            continue;
          }

          // HITL 中断
          if (data.__interrupt__) {
            const interruptValue = data.__interrupt__[0]?.value;
            if (interruptValue?.action_requests) {
              openReview({ threadId: tid, ...interruptValue });
            }
            break;
          }

          // model 节点：agent 决定调用工具
          const modelMsgs: any[] = data?.model?.messages ?? [];
          for (const msg of modelMsgs) {
            const toolCalls = msg?.tool_calls;
            if (Array.isArray(toolCalls) && toolCalls.length > 0) {
              // 先把流式积累的文本 finalize（agent 的前置文字）
              finalizeToken();
              addMessage({
                role: "assistant",
                content: typeof msg.content === "string" ? msg.content : "",
                tool_calls: toolCalls.map((tc: any) => ({
                  id: tc.id ?? "",
                  name: tc.name ?? tc.function?.name ?? "",
                  args: tc.args ?? tc.function?.arguments ?? {},
                })),
              });
            }
          }

          // tools 节点：工具执行结果
          const toolsMsgs: any[] = data?.tools?.messages ?? [];
          for (const msg of toolsMsgs) {
            if (msg?.type === "tool" || msg?.role === "tool") {
              addMessage({
                role: "tool",
                content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content),
                tool_name: msg.name ?? "",
                tool_call_id: msg.tool_call_id ?? "",
              });
            }
          }
        }

        // ── tasks 事件：McpApprovalMiddleware interrupt ──────────
        if (chunk.event === "tasks") {
          const task = chunk.data;
          if (task?.interrupts?.length > 0) {
            const interruptValue = task.interrupts[0]?.value;
            if (interruptValue?.action_requests) {
              openReview({ threadId: tid, ...interruptValue });
              break;
            }
          }
        }

        // ── 自定义进度事件（middleware 发出）──────────────────────
        if (chunk.event === "custom") {
          const status = chunk.data?.status ?? chunk.data?.message;
          if (status) {
            addMessage({ role: "system", content: `⚙️ ${status}` });
          }
        }
      }
      if (reviewStarted) {
        mutate(SKILLS_KEY);
        setTimeout(() => mutate(SKILLS_KEY), 15_000);
      }
    } finally {
      finalizeToken();
      setStreaming(false);
      mutate(THREADS_KEY);
    }
  }, []);

  return { sendMessage, streaming, threadId: currentThreadId };
}
