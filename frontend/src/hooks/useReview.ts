import { client } from "@/lib/client";
import { useReviewStore } from "@/store/reviewStore";
import { useChatStore } from "@/store/chatStore";
import type { ReviewDecision } from "@/types/review";

export function useReview() {
  const { current, closeReview } = useReviewStore();
  const { appendToken, appendThinking, finalizeToken } = useChatStore();

  async function submitDecision(decision: ReviewDecision) {
    if (!current) return;
    const { threadId } = current;

    // 将决策存入 thread state，格式与 HumanInTheLoopMiddleware 的 resume 格式一致
    await client.threads.updateState(threadId, {
      values: decision,  // { decisions: [{ type: "approve" }] }
    });
    closeReview();

    // 以 input=null 重新发起 stream，触发 Command(resume=decision) 恢复执行
    const stream = client.runs.stream(threadId, "choreo", {
      input: null,
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
    }
    finalizeToken();
  }

  return { current, submitDecision };
}
