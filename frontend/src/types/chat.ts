export type AgentRole =
  | 'profiler'
  | 'optimizer'
  | 'news_materiality'
  | 'rate_impact'
  | 'valuation'
  | 'technical'
  | 'chat'

export interface UserMessage {
  id: string
  role: 'user'
  text: string
  createdAt: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  agentRole: AgentRole
  text: string
  isStreaming: boolean
  card?: CardData
  createdAt: string
}

export type Message = UserMessage | AssistantMessage

/* Discriminated union — one payload per agent card type */
export type CardData =
  | { type: 'profiler'; payload: import('./api').ProfileResponse }
  | { type: 'optimizer'; payload: import('./api').PortfolioResponse; mode?: 'suggest' | 'analyze' }
  | { type: 'news'; payload: { items: import('./api').NewsItemResponse[] } }
  | { type: 'rate_impact'; payload: import('./api').RateImpactCardData }
  | { type: 'valuation'; payload: import('./api').ValuationResponse }
  | { type: 'technical'; payload: import('./api').TechnicalResponse }

/* SSE event shapes from backend /chat stream */
export interface ToolEvent {
  event: 'tool'
  tool: string
  status: 'running' | 'done'
}

export interface ContentEvent {
  event: 'content'
  delta: string
}

export interface DoneEvent {
  event: 'done'
  agentRole: AgentRole
}

export interface ErrorEvent {
  event: 'error'
  message: string
}

export type SSEEvent = ToolEvent | ContentEvent | DoneEvent | ErrorEvent
