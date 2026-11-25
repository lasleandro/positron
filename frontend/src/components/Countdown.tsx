import { Timer } from "lucide-react";
import { useEffect, useState } from "react";

import { formatRemaining } from "../lib/format";

/** Visible remaining time; calls onEnd once when it reaches zero. */
export function Countdown({ until, onEnd, prefix = "Acesso termina em" }: { until: number; onEnd?: () => void; prefix?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const left = until - now;
  useEffect(() => {
    if (left <= 0) onEnd?.();
  }, [left <= 0]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <span className={left < 5 * 60 * 1000 ? "countdown soon" : "countdown"} role="timer" aria-live="off">
      <Timer size={15} aria-hidden="true" />{prefix} {formatRemaining(left)}
    </span>
  );
}
