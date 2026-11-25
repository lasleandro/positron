import { MailCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Alert } from "../components/Alert";
import { api } from "../lib/api";
import { errorMessage } from "../lib/format";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setDone((await api.requestPasswordReset(email.trim())).message);
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
        <h1>Verifique seu email</h1>
        <p className="muted">{done}</p>
        <p className="muted">Para manter seus documentos, tenha em mãos o código de recuperação e o autenticador.</p>
      </section>
    );
  }
  return (
    <section className="surface form-card narrow">
      <h1>Esqueci minha senha</h1>
      <p className="muted">Enviaremos um link de redefinição para o email da sua conta.</p>
      <form className="form-grid" onSubmit={submit}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" maxLength={150} required
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <Alert message={error} />
        <button className="button primary" disabled={busy}>Enviar link</button>
      </form>
      <p className="route-link"><Link to="/entrar/">Voltar para o login</Link></p>
    </section>
  );
}
