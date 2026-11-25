import { useEffect, useState } from "react";

import { api } from "./api";

const POLL_MS = 5000;
const BASE_TITLE = "Pode Abrir";

/** Poll @handle requests waiting for the signed-in owner; reflects the count in the tab title. */
export function usePendingRequests(enabled: boolean) {
  const [items, setItems] = useState<{ id: string; pair_until: string }[]>([]);

  useEffect(() => {
    if (!enabled) {
      setItems([]);
      return;
    }
    let stopped = false;
    let timer = 0;
    async function poll() {
      if (document.visibilityState === "visible" || items.length === 0) {
        try {
          const result = await api.pendingRequests();
          if (!stopped) setItems(result.items);
        } catch {
          // Transient failure: keep the last known state and try again.
        }
      }
      if (!stopped) timer = window.setTimeout(poll, POLL_MS);
    }
    poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.title = items.length ? `(${items.length}) ${BASE_TITLE}` : BASE_TITLE;
  }, [items.length]);

  return items;
}
