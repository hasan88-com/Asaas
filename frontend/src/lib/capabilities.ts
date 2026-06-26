/**
 * Asset-class capability map (frontend mirror of backend core/capabilities.py).
 *
 * Single source of truth for which tabs/panels render per asset class. Keep in
 * sync with the backend map — the backend refuses to compute disabled methods,
 * the frontend hides the corresponding tabs so the user never sees an option
 * that doesn't apply (e.g. no Technical tab on a T-bill, no DCF on Bitcoin).
 *
 * Phase 1: reflects currently-implemented methods only. Later phases flip flags
 * on (on-chain for crypto, duration panels for fixed income, etc.).
 *
 * Keyed on the values produced by HoldingDetail's `inferAssetClass`
 * (equity / crypto / commodity / tbill / bond). Unknown classes fall back to
 * equity behaviour so we never wrongly hide a tab.
 */

export interface Capabilities {
  /** Methods the Valuation tab can run; empty hides the Valuation tab. */
  valuationMethods: string[]
  /** Technical (RSI/MACD/etc.) tab; disabled for fixed income. */
  technical: { enabled: boolean; rsi: { overbought: number; oversold: number } }
  /** Risk/structure panels (e.g. "duration" for fixed income). */
  riskPanels: string[]
  /** On-chain panel (crypto only). Phase 2. */
  onchain: boolean
  shariah: 'screenable' | 'compliant' | 'non_compliant' | 'disputed'
  /** Class-level warnings to surface as a banner. */
  warnings: string[]
}

const RSI_DEFAULT = { overbought: 70, oversold: 30 }
const RSI_CRYPTO = { overbought: 80, oversold: 20 }

const EQUITY: Capabilities = {
  valuationMethods: ['dcf', 'multiples'],
  technical: { enabled: true, rsi: RSI_DEFAULT },
  riskPanels: [],
  onchain: false,
  shariah: 'screenable',
  warnings: [],
}

const CRYPTO: Capabilities = {
  valuationMethods: ['market_comparison'],
  technical: { enabled: true, rsi: RSI_CRYPTO },
  riskPanels: [],
  onchain: false,
  shariah: 'disputed',
  warnings: [
    "Crypto's legal status in Pakistan is restrictive and there is no SBP-sanctioned domestic exchange.",
  ],
}

const COMMODITY: Capabilities = {
  valuationMethods: ['market_comparison'],
  technical: { enabled: true, rsi: RSI_DEFAULT },
  riskPanels: [],
  onchain: false,
  shariah: 'compliant',
  warnings: [],
}

const FIXED_INCOME: Capabilities = {
  valuationMethods: ['ytm'],
  technical: { enabled: false, rsi: RSI_DEFAULT },
  riskPanels: ['duration'],
  onchain: false,
  shariah: 'non_compliant',
  warnings: [],
}

const CAPABILITIES: Record<string, Capabilities> = {
  equity: EQUITY,
  psx_stock: EQUITY,
  global_stock: EQUITY,
  mutual_fund: EQUITY,
  crypto: CRYPTO,
  commodity: COMMODITY,
  tbill: FIXED_INCOME,
  bond: FIXED_INCOME,
}

export function getCapabilities(assetClass: string | undefined): Capabilities {
  if (!assetClass) return EQUITY
  return CAPABILITIES[assetClass.toLowerCase()] ?? EQUITY
}
