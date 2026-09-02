export interface DemoChatMessage {
  role: "patient" | "ai";
  content: string;
}

export interface AgentDemoState {
  patientId: string | null;
  conversationId: string | null;
  messages: DemoChatMessage[];
  model: string | null;
  error: string | null;
}

export const initialAgentDemoState: AgentDemoState = {
  patientId: null,
  conversationId: null,
  messages: [],
  model: null,
  error: null,
};

export function normalizeAgentDemoState(state: AgentDemoState | null | undefined): AgentDemoState {
  return {
    ...initialAgentDemoState,
    ...(state ?? {}),
    messages: Array.isArray(state?.messages) ? state.messages : [],
  };
}
