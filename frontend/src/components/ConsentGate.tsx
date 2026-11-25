import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";
import { Alert } from "./Alert";
import { ConsentText } from "./ConsentText";

/** Blocks the owner area until the current Terms + Privacy Policy version is accepted. */
export function ConsentGate({ onLogout }: { onLogout: () => void }) {
  const { session, setSession } = useSession();
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!session.user || session.user.consent_ok) return null;

  async function accept(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSession(await api.acceptConsent(session.legal_version));
    } catch (cause) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  }

  return (
    <div className="consent-gate">
      <form className="surface form-card consent-card" onSubmit={accept} aria-labelledby="consent-title">
        <ShieldCheck size={28} aria-hidden="true" />
        <h2 id="consent-title">Termos e privacidade</h2>
        <p className="muted">
          Para continuar, confirme que leu os <Link to="/termos/">Termos de Uso</Link> e a{" "}
          <Link to="/privacidade/">Política de Privacidade</Link> (versão {session.legal_version}).
        </p>
        <label className="choice consent-choice">
          <input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} required />
          <ConsentText />
        </label>
        <Alert message={error} />
        <div className="actions">
          <button className="button primary" disabled={!checked || busy}>Aceitar e continuar</button>
          <button type="button" className="button ghost" onClick={onLogout}>Sair</button>
        </div>
      </form>
    </div>
  );
}
