import { CircleCheck, TriangleAlert } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Alert } from "../components/Alert";
import { RecoveryCode } from "../components/RecoveryCode";
import { api } from "../lib/api";
import { createAccountKeys, deriveRecovery, openVault, sealVaultWithPassword } from "../lib/crypto";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";
import { PasswordInput } from "../components/PasswordInput";

const MIN_PASSWORD = 14;

function takeTokenFromHash(): string {
  const fragment = location.hash.slice(1);
  if (!/^[A-Za-z0-9_-]{43}$/.test(fragment)) return "";
  history.replaceState(history.state, "", location.pathname + location.search);
  return fragment;
}

export function ResetPassword() {
  const { session } = useSession();
  const [token] = useState(takeTokenFromHash);
  const [account, setAccount] = useState<{ email: string; wrapped_recovery: string } | null>(null);
  const [linkError, setLinkError] = useState(token ? "" : "Link de redefinição inválido.");
  const [lostCode, setLostCode] = useState(false);
  const [acceptLoss, setAcceptLoss] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<"recovery" | "fresh" | null>(null);
  const [newCode, setNewCode] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (token) api.inspectReset(token).then(setAccount, (cause) => setLinkError(errorMessage(cause)));
  }, [token]);

  /** Keep the vault: open the recovery copy here, re-seal it with the new password. */
  async function recoverVault(email: string, wrappedRecovery: string) {
    const recovery = await deriveRecovery(session.vault_namespace, email, recoveryCode);
    const vault = await openVault(recovery.key, wrappedRecovery, "vault-recovery", email).catch(() => {
      throw new Error("Código de recuperação inválido.");
    });
    const sealed = await sealVaultWithPassword(session.vault_namespace, email, password, vault);
    return { password: sealed.authentication, wrapped_password: sealed.wrappedPassword, recovery_proof: recovery.proof };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!account) return;
    if (password !== confirmation) return setError("As senhas não coincidem.");
    setBusy(true);
    setError("");
    try {
      if (lostCode) {
        const keys = await createAccountKeys(session.vault_namespace, account.email, password);
        await api.confirmReset({
          token, otp, mode: "fresh", password: keys.authentication, wrapped_password: keys.wrappedPassword,
          recovery_proof: keys.recoveryProof, wrapped_recovery: keys.wrappedRecovery,
        });
        setNewCode(keys.recoveryCode);
        setDone("fresh");
      } else {
        await api.confirmReset({ token, otp, mode: "recovery", ...(await recoverVault(account.email, account.wrapped_recovery)) });
        setDone("recovery");
      }
      setPassword("");
      setConfirmation("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (linkError) {
    return (
      <section className="surface form-card narrow">
        <h1>Redefinir senha</h1>
        <Alert message={linkError} />
        <p className="route-link"><Link to="/esqueci-senha/">Solicitar outro link</Link></p>
      </section>
    );
  }
  if (done === "recovery") {
    return (
      <section className="surface form-card narrow pairing-card">
        <CircleCheck className="hero-icon" size={40} aria-hidden="true" />
        <h1>Senha redefinida</h1>
        <p className="muted">Seus documentos foram mantidos. As sessões abertas foram encerradas.</p>
        <div className="actions center"><Link className="button primary" to="/entrar/">Entrar</Link></div>
      </section>
    );
  }
  if (done === "fresh" && account) {
    return (
      <section className="surface form-card narrow">
        <h1>Novo cofre criado</h1>
        <p className="muted">A senha foi redefinida e os documentos anteriores foram removidos. Guarde o novo código.</p>
        <div className="form-grid">
          <RecoveryCode code={newCode} email={account.email} saved={saved} onSavedChange={setSaved} />
          {saved && <Link className="button primary" to="/entrar/">Entrar</Link>}
        </div>
      </section>
    );
  }
  if (!account) return null;

  return (
    <section className="surface form-card narrow">
      <h1>Redefinir senha</h1>
      <p className="muted">Conta <strong>{account.email}</strong></p>
      <form className="form-grid" onSubmit={submit}>
        {!lostCode ? (
          <div>
            <label htmlFor="recovery">Código de recuperação</label>
            <input id="recovery" className="mono" autoComplete="off" autoCapitalize="characters" spellCheck={false} required
              placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
              value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} />
            <button type="button" className="button ghost inline" onClick={() => setLostCode(true)}>Perdi meu código</button>
          </div>
        ) : (
          <div className="warning" role="alert">
            <p><TriangleAlert size={18} aria-hidden="true" /><strong>Sem o código, seus documentos atuais não podem ser abertos.</strong></p>
            <p>Ninguém, nem o servidor, consegue decifrá-los. Ao continuar, eles serão apagados e um cofre vazio será criado.</p>
            <label className="choice">
              <input type="checkbox" checked={acceptLoss} onChange={(event) => setAcceptLoss(event.target.checked)} required />
              <span>Entendo que meus documentos atuais serão apagados.</span>
            </label>
            <button type="button" className="button ghost inline" onClick={() => { setLostCode(false); setAcceptLoss(false); }}>
              Tenho o código
            </button>
          </div>
        )}
        <div>
          <label htmlFor="new-password">Nova senha</label>
          <PasswordInput id="new-password" autoComplete="new-password" minLength={MIN_PASSWORD} maxLength={256} required
            value={password} onChange={(event) => setPassword(event.target.value)} />
        </div>
        <div>
          <label htmlFor="confirm-password">Confirme a nova senha</label>
          <PasswordInput id="confirm-password" autoComplete="new-password" minLength={MIN_PASSWORD} maxLength={256} required
            value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
        </div>
        <div>
          <label htmlFor="otp">Código do autenticador</label>
          <input id="otp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
            value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} />
        </div>
        <Alert message={error} />
        <button className={lostCode ? "button danger" : "button primary"} disabled={busy || (lostCode && !acceptLoss)}>
          {lostCode ? "Apagar documentos e redefinir" : "Redefinir senha"}
        </button>
      </form>
    </section>
  );
}
