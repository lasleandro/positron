import { MailCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { Alert } from "../components/Alert";
import { RecoveryCode } from "../components/RecoveryCode";
import { api, ApiError, type AuthenticatorSetup } from "../lib/api";
import { createAccountKeys } from "../lib/crypto";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";
import { PasswordInput } from "../components/PasswordInput";

const MIN_PASSWORD = 14;

/** Invite links carry the token in the URL fragment, which never reaches server logs. */
function takeTokenFromHash(): string {
  const fragment = location.hash.slice(1);
  if (!/^[A-Za-z0-9_-]{43}$/.test(fragment)) return "";
  history.replaceState(history.state, "", location.pathname + location.search);
  return fragment;
}

/** No invite link: the first account requests its own invitation with the installation code. */
function FirstAccess() {
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function request(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSentTo((await api.bootstrapInvitation(code.trim(), email.trim())).email);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (sentTo) {
    return (
      <section className="surface form-card narrow pairing-card">
        <MailCheck className="hero-icon" size={40} aria-hidden="true" />
        <h1>Verifique seu email</h1>
        <p className="muted">Enviamos o link de cadastro para <strong>{sentTo}</strong>. Abra-o neste navegador.</p>
      </section>
    );
  }
  return (
    <section className="surface form-card narrow">
      <h1>Criar conta</h1>
      <p className="muted">
        O cadastro é feito pelo link de convite enviado ao seu email. Abra o link recebido para continuar.
      </p>
      <details>
        <summary>Primeira conta desta instalação</summary>
        <form className="form-grid" onSubmit={request}>
          <div>
            <label htmlFor="install-code">Código de instalação</label>
            <input id="install-code" className="mono" autoComplete="off" maxLength={43} required
              value={code} onChange={(event) => setCode(event.target.value)} />
          </div>
          <div>
            <label htmlFor="email">Seu email</label>
            <input id="email" type="email" autoComplete="email" maxLength={150} required
              value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <Alert message={error} />
          <button className="button primary" disabled={busy}>Enviar convite para meu email</button>
        </form>
      </details>
      <p className="route-link"><Link to="/entrar/">Já tenho conta</Link></p>
    </section>
  );
}

export function Enroll() {
  const { session, setSession } = useSession();
  const { rememberVault } = useVault();
  const navigate = useNavigate();
  const [token] = useState(takeTokenFromHash);
  const [email, setEmail] = useState("");
  const [inviteError, setInviteError] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [otp, setOtp] = useState("");
  const [setup, setSetup] = useState<AuthenticatorSetup | null>(null);
  const [recoveryCode, setRecoveryCode] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const vault = useRef("");

  useEffect(() => {
    if (!token) return;
    api.inspectInvitation(token).then((invite) => setEmail(invite.email), (cause) => setInviteError(errorMessage(cause)));
  }, [token]);

  if (session.user && !setup) return <Navigate to="/documentos/" replace />;
  if (!token) return <FirstAccess />;

  async function start(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmation) {
      setError("As senhas não coincidem.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const keys = await createAccountKeys(session.vault_namespace, email, password);
      setSetup(await api.enroll(token, keys.authentication, {
        wrapped_password: keys.wrappedPassword,
        wrapped_recovery: keys.wrappedRecovery,
        recovery_proof: keys.recoveryProof,
      }));
      vault.current = keys.vault;
      setRecoveryCode(keys.recoveryCode);
      setPassword("");
      setConfirmation("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!setup) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.confirmEnrollment(otp);
      rememberVault(setup.email, vault.current);
      vault.current = "";
      setSession(updated);
      navigate("/documentos/", { replace: true });
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "enrollment_expired") setSetup(null);
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (inviteError) {
    return (
      <section className="surface form-card narrow">
        <h1>Convite indisponível</h1>
        <Alert message={inviteError} />
        <p className="muted">Peça um novo convite a quem o enviou. Cada link vale uma vez.</p>
      </section>
    );
  }

  if (setup) {
    return (
      <section className="surface form-card narrow">
        <p className="eyebrow">Passo 2 de 2</p>
        <h1>Proteja sua conta</h1>
        <form className="form-grid" onSubmit={confirm}>
          <RecoveryCode code={recoveryCode} email={setup.email} saved={saved} onSavedChange={setSaved} />
          <section>
            <h2>Microsoft Authenticator</h2>
            <p className="muted">Toque em +, escolha Outra conta e escaneie o QR.</p>
            <img className="qr" src={setup.qr} width={224} height={224} alt="QR para cadastrar a conta no autenticador" />
            <details>
              <summary>Estou usando o mesmo celular</summary>
              <p>Escolha inserir manualmente e copie esta chave.</p>
              <code className="selectable">{setup.secret}</code>
            </details>
          </section>
          <div>
            <label htmlFor="otp">Código de 6 dígitos</label>
            <input id="otp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
              value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} />
          </div>
          <Alert message={error} />
          <button className="button primary" disabled={busy || !saved}>Confirmar e criar conta</button>
        </form>
      </section>
    );
  }

  return (
    <section className="surface form-card narrow">
      <p className="eyebrow">Passo 1 de 2</p>
      <h1>Criar conta</h1>
      <p className="muted">Escolha a senha que vai proteger seus documentos neste e em outros dispositivos.</p>
      <form className="form-grid" onSubmit={start}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" readOnly value={email} />
        </div>
        <div>
          <label htmlFor="new-password">Senha</label>
          <PasswordInput id="new-password" autoComplete="new-password" minLength={MIN_PASSWORD} maxLength={256} required
            value={password} onChange={(event) => setPassword(event.target.value)} />
          <small>Pelo menos {MIN_PASSWORD} caracteres.</small>
        </div>
        <div>
          <label htmlFor="confirm-password">Confirme a senha</label>
          <PasswordInput id="confirm-password" autoComplete="new-password" minLength={MIN_PASSWORD} maxLength={256} required
            value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
        </div>
        <Alert message={error} />
        <button className="button primary" disabled={busy || !email}>{busy ? "Gerando chaves…" : "Continuar"}</button>
      </form>
      <p className="route-link"><Link to="/entrar/">Já tenho conta</Link></p>
    </section>
  );
}
