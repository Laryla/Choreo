// HumanInTheLoopMiddleware 触发 interrupt 时的 payload 格式
export interface ActionRequest {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface ReviewConfig {
  action_name: string;
  allowed_decisions: string[];
}

export interface ReviewRequest {
  threadId: string;
  action_requests: ActionRequest[];
  review_configs: ReviewConfig[];
}

// 发送给后端的决策格式（对应 HumanInTheLoopMiddleware 的 resume 格式）
export type DecisionType = "approve" | "edit" | "reject";

export interface EditedAction {
  name: string;
  args: Record<string, unknown>;
}

export interface Decision {
  type: DecisionType;
  message?: string;           // reject 时附带原因
  edited_action?: EditedAction; // edit 时附带修改内容
}

export interface ReviewDecision {
  decisions: Decision[];
}
