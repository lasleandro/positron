import { createContext, useCallback, useContext, useRef, useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError } from "./api";
import { aesKey, decode, deriveCredentials, encode, openVault, STORAGE } from "./crypto";
import { useSession } from "./session";
import { PasswordInput } from "../components/PasswordInput";

/**
 * Holds the vault key for this tab. The random vault key is opened in the browser from the
 * copy sealed by the password key and kept in sessionStorage (cleared when the tab closes).
 */

interface SavedVault { email: string; vault: string }
type VaultAction = <T>(action: (vault: CryptoKey) => Promise<T>) => Promise<T>;

interface VaultContextValue {
  withVault: VaultAction;
  rememberVault: (email: string, vault: string) => void;
  forgetVault: () => void;
}

const VaultContext = createContext<VaultContextValue | null>(null);

function readSaved(): SavedVault | null {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE.vault) || "null");
  } catch {
    return null;
  }
}

export function VaultProvider({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const dialog = useRef<HTMLDialogElement>(null);
  const pending = useRef<{ resolve: (key: CryptoKey) => void; reject: (error: Error) => void } | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const email = session.user?.email ?? "";

  const rememberVault = useCallback((owner: string, vault: string) => {
    sessionStorage.setItem(STORAGE.vault, JSON.stringify({ email: owner, vault }));
  }, []);
  const forgetVault = useCallback(() => sessionStorage.removeItem(STORAGE.vault), []);

  const vaultKey = useCallback((): Promise<CryptoKey> => {
    const saved = readSaved();
    if (saved?.email === email) return aesKey(decode(saved.vault));
    return new Promise((resolve, reject) => {
      pending.current = { resolve, reject };
      setError("");
      dialog.current?.showModal();
    });
  }, [email]);

  const withVault: VaultAction = useCallback(async (action) => {
    const key = await vaultKey();
    try {
      return await action(key);
    } catch (cause) {
      if (cause instanceof Error && cause.name === "OperationError") {
        forgetVault();
        throw new Error("Não foi possível abrir o cofre. Confira sua senha e tente novamente.");
      }
      throw cause;
    }
  }, [vaultKey, forgetVault]);

  function close(outcome: CryptoKey | Error) {
    dialog.current?.close();
    setPassword("");
    const waiting = pending.current;
    pending.current = null;
    if (outcome instanceof Error) waiting?.reject(outcome);
    else waiting?.resolve(outcome);
  }

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { authentication, passwordKey } = await deriveCredentials(session.vault_namespace, email, password);
      const { wrapped_vault: wrapped } = await api.verifyVault(authentication);
      const vault = await openVault(passwordKey, wrapped, "vault-password", email);
      rememberVault(email, encode(vault));
      close(await aesKey(vault));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Não foi possível abrir o cofre.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <VaultContext.Provider value={{ withVault, rememberVault, forgetVault }}>
      {children}
      <dialog ref={dialog} className="vault-dialog" onCancel={() => close(new Error("Abertura do cofre cancelada."))}>
        <form className="form-grid" onSubmit={unlock}>
          <h2>Abrir o cofre neste navegador</h2>
          <p className="muted">A senha nunca sai deste dispositivo. Ela abre a chave dos seus documentos.</p>
          <label htmlFor="vault-password">Senha da sua conta</label>
          <PasswordInput id="vault-password" autoComplete="current-password" required
            value={password} onChange={(event) => setPassword(event.target.value)} autoFocus />
          {error && <p className="alert" role="alert">{error}</p>}
          <div className="actions">
            <button className="button primary" disabled={busy}>Desbloquear</button>
            <button type="button" className="button ghost" onClick={() => close(new Error("Abertura do cofre cancelada."))}>
              Cancelar
            </button>
          </div>
        </form>
      </dialog>
    </VaultContext.Provider>
  );
}

export function useVault(): VaultContextValue {
  const value = useContext(VaultContext);
  if (!value) throw new Error("useVault outside VaultProvider");
  return value;
}
