import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { isInstallSnoozed, isPhone, snoozeInstall, useInstallPrompt } from "../lib/pwa";
import { useSession } from "../lib/session";
import { COOKIE_NOTICE_EVENT, cookieNoticeAcknowledged } from "./CookieNotice";

/** One-time, dismissible "install the app" card on phones (snoozed 30 days after a dismissal). */
export function InstallBanner() {
  const { status, promptInstall } = useInstallPrompt();
  const { session } = useSession();
  const [hidden, setHidden] = useState(() => !isPhone() || isInstallSnoozed());
  // Never stack with the cookie notice: wait until it has been acknowledged.
  const [cookiesSeen, setCookiesSeen] = useState(() => cookieNoticeAcknowledged(session.legal_version));
  useEffect(() => {
    const onSeen = () => setCookiesSeen(true);
    window.addEventListener(COOKIE_NOTICE_EVENT, onSeen);
    return () => window.removeEventListener(COOKIE_NOTICE_EVENT, onSeen);
  }, []);
  if (hidden || !cookiesSeen || status === "installed") return null;
  const dismiss = () => {
    snoozeInstall();
    setHidden(true);
  };
  return (
    <aside className="install-banner" aria-label="Instalar o app">
      <img src="/icon-192.png" alt="" width={40} height={40} />
      <div className="install-copy">
        <strong>Instale o pode abrir</strong>
        <span>Abra pela tela inicial e receba avisos de pedidos de leitura.</span>
        <div className="install-actions">
          {status === "available"
            ? <button type="button" className="button primary" onClick={() => void promptInstall()}><Download size={16} aria-hidden="true" />Instalar</button>
            : <Link className="button primary" to="/instalar/">Ver como</Link>}
          <button type="button" className="button ghost" onClick={dismiss}>Agora não</button>
        </div>
      </div>
      <button type="button" className="icon-button install-close" onClick={dismiss} aria-label="Dispensar"><X size={16} /></button>
    </aside>
  );
}
