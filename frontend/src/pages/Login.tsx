import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { Alert } from "../components/Alert";
import { api } from "../lib/api";
import { deriveCredentials, encode, openVault } from "../lib/crypto";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";
import { PasswordInput } from "../components/PasswordInput";

/** Only same-app paths are accepted as a post-login destination (no open redirect). */
function safeNext(value: string | null): string {
  return value && /^\/[a-z0-9/_-]*$/i.test(value) && !value.startsWith("//") ? value : "/documentos/";
}

export function Login() {
  const { session, setSession } = useSession();
  const { rememberVault, forgetVault } = useVault();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = safeNext(params.get("next"));
  const pairing = next.startsWith("/autorizar");

  if (session.user) return <Navigate to={next} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!crypto.subtle) {
      setError("Abra o aplicativo em HTTPS em um navegador atualizado.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const owner = email.trim().toLowerCase();
      const { authentication, passwordKey } = await deriveCredentials(session.vault_namespace, owner, password);
      forgetVault();
      const updated = await api.login(owner, authentication, otp);
      const vault = await openVault(passwordKey, updated.wrapped_vault, "vault-password", owner);
      rememberVault(owner, encode(vault));
      setSession(updated);
      navigate(next, { replace: true });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <>
    <section className="surface form-card narrow">
      <h1>Entrar</h1>
      <p className="muted">
        {pairing ? "Entre no celular para autorizar a leitura." : "Acesse seus documentos."}
      </p>
      <form className="form-grid" onSubmit={submit}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" autoCapitalize="none" maxLength={150} required
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div>
          <label htmlFor="password">Senha</label>
          <PasswordInput id="password" autoComplete="current-password" maxLength={256} required
            value={password} onChange={(event) => setPassword(event.target.value)} />
        </div>
        <div>
          <label htmlFor="otp">Código do app autenticador</label>
          <input id="otp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
            value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} />
        </div>
        <Alert message={error} />
        <button className="button primary" disabled={busy}>{busy ? "Derivando chave…" : "Entrar"}</button>
      </form>
      <p className="route-link">
        <Link to="/esqueci-senha/">Esqueci minha senha</Link> · <Link to="/solicitar-acesso/">Solicitar acesso</Link> · <Link to="/ler/">Ler documentos</Link>
      </p>
      <p className="route-link subtle"><Link to="/cadastro/">Primeiro acesso com convite ou código de instalação</Link></p>
    </section>
    <p className="app-version">Versão {__APP_VERSION__}</p>
    </>
  );
}
