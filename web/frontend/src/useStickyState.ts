import { useEffect, useState } from "react";

const PREFIX = "tradingagents:";

/**
 * useState that survives a reload, for form settings you re-pick every run.
 *
 * Deliberately not used for ticker or analysis date — those are per-run inputs,
 * and silently restoring a stale one invites analyzing the wrong thing.
 */
export function useStickyState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(PREFIX + key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial; // private mode, quota, or hand-edited garbage
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch {
      /* persistence is a convenience, never block the run on it */
    }
  }, [key, value]);

  return [value, setValue] as const;
}
