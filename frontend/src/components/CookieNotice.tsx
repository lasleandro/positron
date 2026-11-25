import { Cookie } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useSession } from "../lib/session";

export const COOKIE_NOTICE_EVENT = "podeabrir:cookies-acknowledged";
const slot = (version: string) => `podeabrir:cookies:${version}`;

export function cookieNoticeAcknowledged(version: string): boolean {
  try {
    return localStorage.getItem(slot(version)) === "1";
  } catch {
    return false;
  }
}

/** Informative notice: only strictly necessary cookies exist, so there is nothing to opt into. */
export function CookieNotice() {
  const { session } = useSession();
  const [visible, setVisible] = useState(() => !cookieNoticeAcknowledged(session.legal_version));
  if (!visible) return null;
  function acknowledge() {
    try {
      localStorage.setItem(slot(session.legal_version), "1");
    } catch {
      // Storage blocked: the notice simply shows again next visit.
    }
    setVisible(false);
    window.dispatchEvent(new Event(COOKIE_NOTICE_EVENT));
  }
  return (
    <aside className="cookie-notice" aria-label="Aviso de cookies">
      <Cookie size={20} aria-hidden="true" />
      <p>
        Usamos apenas cookies essenciais, para manter sua sessão e proteger o acesso. Nada de publicidade ou
        rastreamento. <Link to="/privacidade/#cookies">Saiba mais</Link>
      </p>
      <button type="button" className="button primary" onClick={acknowledge}>Entendi</button>
    </aside>
  );
}
