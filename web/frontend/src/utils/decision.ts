/**
 * Client-side preview parser for the streaming `final_trade_decision` section.
 *
 * Mirrors the server-side classifier in
 * `tradingagents/graph/signal_processing.py`: pick up BUY/HOLD/SELL keywords
 * (plus OVERWEIGHT/UNDERWEIGHT) so the UI can show a tentative decision
 * badge before the authoritative `done` event arrives.
 *
 * Returns null when no clear keyword is found yet.
 */
export function previewDecision(content: string | undefined): string | null {
  if (!content) return null;
  const upper = content.toUpperCase();
  // Prefer the *last* match — the Portfolio Manager's verdict typically lands
  // at the end of the streamed section, after the analysts' rebuttals.
  const matches = upper.match(/\b(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT)\b/g);
  if (!matches || matches.length === 0) return null;
  return matches[matches.length - 1];
}
