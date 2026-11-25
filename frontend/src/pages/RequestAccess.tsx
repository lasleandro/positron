import { MailCheck, Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Alert } from "../components/Alert";
import { api } from "../lib/api";
import { CONTACT_EMAIL } from "../lib/brand";
import { errorMessage } from "../lib/format";

/** Until self-signup exists, requests go to the team inbox, which answers with an invitation. */
export function RequestAccess() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState("");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setDone((await api.requestAccess({ email: email.trim(), name: name.trim(), message: message.trim(), website })).message);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <section className="surface form-card narrow pairing-card">
        <MailCheck className="hero-icon" size={40} aria-hidden="true" />
        <h1>Solicitação enviada</h1>
        <p className="muted">{done}</p>
        <p className="route-link"><Link to="/">Voltar para o início</Link></p>
      </section>
    );
  }
  return (
    <section className="surface form-card narrow">
      <h1>Solicitar acesso</h1>
      <p className="muted">
        O cadastro é feito por convite. Conte quem é você e a equipe envia o convite para o seu e-mail.
      </p>
      <form className="form-grid" onSubmit={submit}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" maxLength={150} required
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div>
          <label htmlFor="name">Nome (opcional)</label>
          <input id="name" autoComplete="name" maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div>
          <label htmlFor="message">Como pretende usar (opcional)</label>
          <textarea id="message" rows={4} maxLength={1000} value={message} onChange={(event) => setMessage(event.target.value)}
            placeholder="Ex.: guardar exames da família, compartilhar documentos com clientes…" />
        </div>
        <div className="honeypot" aria-hidden="true">
          <label htmlFor="website">Site</label>
          <input id="website" tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
        </div>
        <p className="note">Usaremos estes dados só para responder à sua solicitação. Veja a <Link to="/privacidade/">Política de Privacidade</Link>.</p>
        <Alert message={error} />
        <button className="button primary" disabled={busy}><Send size={16} aria-hidden="true" />Enviar solicitação</button>
      </form>
      <p className="route-link">Prefere e-mail? <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> · <Link to="/entrar/">Já tenho conta</Link></p>
    </section>
  );
}
