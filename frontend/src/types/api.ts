/* ------------------------------------------------------------------ */
/* Auth                                                                */
/* ------------------------------------------------------------------ */
export interface UserResponse {
  id: string
  email: string
  full_name?: string
}

/* ------------------------------------------------------------------ */
/* Questionnaire                                                        */
/* ------------------------------------------------------------------ */
export interface QuestionOption {
  value: string
  label: string
}

export interface QuestionDefinition {
  id: string
  question: string
  category: string
  multiple: boolean
  options: QuestionOption[]
  conditional_on?: Record<string, string>
}

export interface InvestmentPreferences {
  shariah: boolean
  asset_classes: string[]
  psx_sectors: string[]
  crypto_assets: string[]
  fixed_income_products: string[]
}

export interface QuestionnaireResponse {
  profile_id: string
  risk_score: number
  investor_persona: string
  risk_tolerance: string
  horizon: string
  investor_mode: string
  goal: string
  constraints: Record<string, unknown>
  investment_preferences?: InvestmentPreferences
  monthly_contribution?: string
  investment_frequency?: string
  agent_remarks?: Record<string, string>
  recommendations?: Record<string, unknown>
}

export interface DeclareHoldingInput {
  instrument_id: string
  quantity: string
  entry_price: string
  entry_date?: string
}

/* ------------------------------------------------------------------ */
/* Performance                                                          */
/* ------------------------------------------------------------------ */
export interface PerformanceResponse {
  pnl_absolute: string
  pnl_percent: string
  total_value?: string     // current total portfolio value (PKR)
  total_cost?: string      // total entry cost (PKR)
  stale?: boolean          // true = served from last snapshot; re-fetch ?live=true to flip
  as_of?: string           // snapshot date when stale
  history: { date: string; value: string; pnl_pct?: string }[]
  holdings_performance?: Array<{
    symbol: string | null
    name?: string | null
    asset_class?: string | null
    quantity?: string
    current_price: string | null
    entry_price: string
    value?: string         // current PKR value of this holding (qty × price)
    weight?: string        // share of total value (0–1)
    pnl_pct: string
    stale: boolean
  }>
}

/* ------------------------------------------------------------------ */
/* Risk analytics                                                       */
/* ------------------------------------------------------------------ */
export interface RiskMetric {
  value: number | null
  as_of: string
  source: string
  stale: boolean
}

export interface RiskMetricsResponse {
  insufficient_data?: boolean
  reason?: string
  observations?: number
  as_of?: string
  var_95?: RiskMetric
  var_99?: RiskMetric
  var_95_parametric?: RiskMetric
  cvar_95?: RiskMetric
  max_drawdown?: RiskMetric
  max_drawdown_days?: RiskMetric
  rolling_vol_30?: RiskMetric
  rolling_sharpe_30?: RiskMetric
  sortino?: RiskMetric
  beta_vs_kse_proxy?: RiskMetric
}

/* ------------------------------------------------------------------ */
/* Diversification                                                      */
/* ------------------------------------------------------------------ */
export interface DiversificationResponse {
  by_sector: Record<string, number>
  by_asset_class: Record<string, number>
  warnings: string[]
}

/* ------------------------------------------------------------------ */
/* Guest analyze                                                        */
/* ------------------------------------------------------------------ */
export interface GuestHoldingPayload {
  symbol: string
  qty: number
  entry_price: number
  asset_class: 'equity' | 'tbill' | 'bond' | 'crypto' | 'commodity'
  interest_rate_at_buy?: number
  buy_date?: string
}

export interface GuestAnalyzeResponse {
  current_metrics: {
    num_holdings?: number
    asset_classes?: Record<string, number>
    diversification_score?: number
    concentration_warnings?: string[]
    weights?: Record<string, number>
    symbol_classes?: Record<string, string>
    expected_return?: number
    volatility?: number
    sharpe?: number
    total_pnl_pct?: number
    holdings_detail?: Array<{
      symbol: string
      asset_class: string
      current_weight: number
      pnl_pct: number
    }>
  }
  suggested_portfolio: import('./api').PortfolioResponse
  rationale: string
  rebalance_actions: string[]
}

/* ------------------------------------------------------------------ */
/* Market search                                                        */
/* ------------------------------------------------------------------ */
export interface InstrumentSearchResult {
  id: string
  symbol: string
  name: string
  asset_class: string
}

/* ------------------------------------------------------------------ */
/* Profile                                                             */
/* ------------------------------------------------------------------ */
export interface ProfileResponse {
  id: string
  user_id: string
  risk_tolerance: 'conservative' | 'moderately_conservative' | 'moderate' | 'aggressive' | 'very_aggressive'
  horizon: 'short' | 'medium' | 'long'
  investor_mode: string
  initial_capital: string
  monthly_contribution?: string
  investment_frequency?: string
  goal: string
  constraints?: Record<string, unknown>
  investment_preferences?: InvestmentPreferences
  risk_willingness?: string
  loss_tolerance?: string
  experience?: string
  updated_at?: string
  investor_persona?: string
  risk_score?: number
  diversification_score?: number
  portfolio_health_score?: number
  crypto_exposure_score?: number
  fixed_income_suitability?: number
  agent_remarks?: Record<string, string>
  recommendations?: Record<string, unknown>
}

/* ------------------------------------------------------------------ */
/* Portfolio Recommendation                                             */
/* ------------------------------------------------------------------ */
export interface PortfolioRecommendationResponse {
  id: string
  user_id: string
  risk_profile_id: string
  risk_score: number
  investor_persona: string
  recommended_allocation: Record<string, number>
  expected_return_range?: string
  expected_volatility?: string
  rebalance_frequency?: string
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Portfolio / Holdings                                                 */
/* ------------------------------------------------------------------ */
export interface HoldingResponse {
  id: string
  portfolio_id: string
  instrument_id: string
  asset_class?: string
  symbol?: string
  name?: string
  target_weight?: number
  actual_weight?: number
  weight: number           // computed: actual_weight ?? target_weight ?? 0
  quantity?: number
  entry_price?: number
  entry_date?: string
  expected_return?: number
  risk?: number
  current_price?: number
}

export interface PortfolioResponse {
  id: string
  user_id: string
  name?: string
  status?: string
  holdings: HoldingResponse[]
  expected_return: string   // Decimal as string
  expected_risk: string     // Decimal as string — matches backend expected_risk
  sharpe: string            // Decimal as string
  risk_free_rate?: string
  rationale?: string
  concentration_warning?: string
  has_existing_holdings?: boolean
  created_at: string
  confirmed_at?: string
}

/* ------------------------------------------------------------------ */
/* News                                                                 */
/* ------------------------------------------------------------------ */
export interface NewsItemResponse {
  id: string
  headline: string
  source: string
  url?: string
  published_at: string
  impact: 'positive' | 'negative' | 'neutral'      // matches backend 'impact'
  impact_level: 'direct' | 'sector' | 'macro'      // matches backend 'impact_level'
  affected_symbols?: string[]
  materiality_score?: number
  summary?: string
}

export interface NewsScrapeStatus {
  state: 'idle' | 'running' | 'done'
  sources_total?: number
  sources_done?: number
  started_at?: string
  ingested?: number
}

/* ------------------------------------------------------------------ */
/* Market sentiment                                                     */
/* ------------------------------------------------------------------ */
export interface SentimentRow {
  scope?: 'market' | 'sector' | 'asset_class'
  label: string
  score: number            // -1 (bearish) … +1 (bullish)
  item_count: number
  bullish_count: number
  bearish_count: number
}

export interface MarketSentimentResponse {
  as_of: string | null
  market: SentimentRow | null
  sectors: SentimentRow[]
  asset_classes: SentimentRow[]
}

/* ------------------------------------------------------------------ */
/* Flags                                                                */
/* ------------------------------------------------------------------ */
export interface FlagResponse {
  id: string
  portfolio_id: string
  news_id?: string
  news_item?: NewsItemResponse
  type: string            // 'news' / 'rate_impact' / 'drift'
  category: string        // alias for type, used by UI
  severity: 'high' | 'medium'
  message: string
  status: string          // 'pending' / 'acknowledged' / 'actioned'
  created_at: string
  resolved_at?: string
  dismissed: boolean      // computed: status !== 'pending'
}

/* ------------------------------------------------------------------ */
/* Rate-impact card                                                     */
/* ------------------------------------------------------------------ */
export interface RateImpactCardData {
  sbp_rate_before: string
  sbp_rate_after: string
  rate_delta: string
  price_impact_pct?: string
  yield_impact_pct?: string
  value_before?: string
  value_after?: string
  is_material: boolean
}

/* ------------------------------------------------------------------ */
/* Valuation                                                            */
/* ------------------------------------------------------------------ */
export interface DCFResult {
  insufficient_data?: boolean
  intrinsic_value_per_share?: string
  wacc?: string
  terminal_growth_rate?: string
  risk_free_is_placeholder?: boolean   // true = no live/cached/last-good SBP rate; WACC unreliable
}

export interface DurationResult {
  macaulay_years: string
  modified_years: string
  dv01: string                  // rupee P&L per 1bp move (on face value)
  convexity: string
  price: string                 // PV of cash flows at YTM
  price_change_per_100bps: string
  frequency: number             // coupons per year assumed
}

export interface MonteCarloResult {
  insufficient_data?: boolean
  p10?: string
  p50?: string
  p90?: string
  num_simulations?: number
}

export interface MultiplesResult {
  pe_ratio?: string
  ev_ebitda?: string
  pb_ratio?: string
  peer_pe_median?: string
  peer_ev_ebitda_median?: string
  // Intrinsic (Gordon) fair value + justified P/E — headline valuation
  eps?: string
  intrinsic_fair_value?: string | null
  justified_pe?: string | null
  wacc?: string
  cost_of_equity?: string
  terminal_growth?: string
  flags?: string[]
  // Sector-multiple cross-check + instrument metadata
  industry_pe?: string
  industry_pe_source?: string
  sector_fair_value?: string | null
  fair_value?: string
  verdict?: string | null
  asset_class?: string | null
  sector?: string | null
  current_price?: string
}

export interface MarketComparisonResult {
  insufficient_data?: boolean
  reason?: string
  current_price?: string
  sma_30?: string
  sma_90?: string
  high_52w?: string
  low_52w?: string
  range_position_pct?: string
}

export interface FixedIncomeResult {
  insufficient_data?: boolean
  reason?: string
  benchmark_yield?: string
  source?: string
  symbol?: string
  face_value?: string | null
  accrued_value?: string | null
  remaining_return?: string | null
  ytm?: string
  sbp_rate?: string
  spread_bps?: number
  days_held?: number | null
  days_remaining?: number | null
  maturity_date?: string | null
  verdict?: 'above_market' | 'below_market' | 'at_market'
  duration?: DurationResult | null
  risk_free_is_placeholder?: boolean   // true = SBP benchmark is a flagged placeholder
}

export interface ValuationResponse {
  symbol: string
  /** Which valuation method the backend ran, based on asset class. */
  method?: 'dcf' | 'market_comparison' | 'yield_to_maturity'
  company_info: {
    name: string
    sector?: string
    current_price?: string
    market_cap?: string
    beta?: string
  }
  dcf: DCFResult
  monte_carlo: MonteCarloResult
  multiples: MultiplesResult
  market_comparison?: MarketComparisonResult
  fixed_income?: FixedIncomeResult
}

/* ------------------------------------------------------------------ */
/* Technical analysis                                                   */
/* ------------------------------------------------------------------ */
export interface TechnicalResponse {
  symbol: string
  insufficient_data?: boolean
  disabled?: boolean        // true = technicals don't apply to this asset class (fixed income)
  reason?: string           // explanation when disabled
  asset_class?: string
  rsi_overbought?: number   // class-aware band (crypto 80/20 vs default 70/30)
  rsi_oversold?: number
  rsi?: number
  macd?: number
  macd_signal?: number
  macd_hist?: number
  mfi?: number
  sma_20?: number
  sma_50?: number
  sma_200?: number
  ema_20?: number
  ema_50?: number
  support?: number
  resistance?: number
  crossover?: 'golden_cross' | 'death_cross' | null
}

/* ------------------------------------------------------------------ */
/* Chat history                                                         */
/* ------------------------------------------------------------------ */
export interface ChatHistoryItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  tool_calls?: Record<string, unknown>
  agent_role?: string  // computed client-side: 'chat' for assistant messages
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Debt market                                                          */
/* ------------------------------------------------------------------ */
export interface DebtInstrument {
  security_code: string
  security_name: string
  face_value: number | null
  listing_date: string
  issue_date: string
  issue_size: number | null
  maturity_date: string
  coupon_rate: number | null
  prev_coupon_date: string
  next_coupon_date: string
  outstanding_days: number | null
  remaining_years: number | null
  category: string
}

/* ------------------------------------------------------------------ */
/* Watchlist — stocks / commodities / debt / crypto                     */
/* ------------------------------------------------------------------ */
export interface WatchlistItem {
  id: string
  symbol: string
  name: string
  asset_class: string   // psx_stock / global_stock / crypto / tbill / commodity / mutual_fund
  sector?: string | null
  currency: string
  price?: string | null  // Decimal as string, native quote currency (PKR for PSX, USD for crypto/commodity)
  created_at: string
}

export interface WatchlistResponse {
  items: WatchlistItem[]
}

export interface QuoteResponse {
  symbol: string
  asset_class: string
  price_pkr: string | null   // Decimal as string, already PKR-converted; null when no quote (e.g. debt)
  as_of: string
}

/* ------------------------------------------------------------------ */
/* Raabta AI — conversations                                           */
/* ------------------------------------------------------------------ */
export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Wallet — virtual PKR cash                                           */
/* ------------------------------------------------------------------ */
export interface WalletResponse {
  balance: string   // Decimal as string
  currency: string
  created_at: string
}

export type CashTransactionType = 'deposit' | 'withdrawal' | 'buy' | 'sell'

export interface CashTransaction {
  id: string
  type: CashTransactionType
  amount: string          // Decimal as string, always positive; sign implied by type
  balance_after: string
  symbol?: string | null
  quantity?: string | null
  price?: string | null
  status: string
  note?: string | null
  created_at: string
}

export interface TransactionListResponse {
  items: CashTransaction[]
  total: number
}
