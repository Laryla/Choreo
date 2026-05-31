import { client } from "@/lib/client";
import { useReviewStore } from "@/store/reviewStore";
import { useChatStore } from "@/store/chatStore";
import type { ReviewDecision } from "@/types/review";

export function useReview() {
  const { current, openReview, closeReview } = useReviewStore();
  const { appendToken, appendThinking, finalizeToken } = useChatStore();

  async function submitDecision(decision: ReviewDecision) {
    if (!current) return;
    const { threadId } = current;

    // 将决策存入 thread state，格式与 HumanInTheLoopMiddleware 的 resume 格式一致
    await client.threads.updateState(threadId, { values: decision } as any);
    closeReview();

    // 以 input=null 重新发起 stream，触发 Command(resume=decision) 恢复执行
    const stream = client.runs.stream(threadId, "choreo", {
      input: null,
      streamMode: ["messages", "updates"],
    } as any);

    for await (const chunk of stream as any) {
      if (chunk.event === "messages") {
        const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
        for (const msg of msgs) {
          if (!msg) continue;
          const reasoning = msg.additional_kwargs?.reasoning_content;
          if (reasoning) appendThinking(reasoning);
          const content = msg.content;
          if (typeof content === "string" && content) appendToken(content);
        }
      }

      // 恢复后如果再次触发 HITL（如多个 mcp_call），重新弹出面板
      if (chunk.event === "updates") {
        const data = chunk.data ?? {};
        if (data.__interrupt__) {
          const interruptValue = data.__interrupt__[0]?.value;
          if (interruptValue?.action_requests) {
            openReview({ threadId, ...interruptValue });
          }
          break;
        }
      }
    }
    finalizeToken();
  }

  return { current, submitDecision };
}
