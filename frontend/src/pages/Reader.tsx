import { AtSign, MonitorSmartphone, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { Alert } from "../components/Alert";
import { ReaderView, type ReaderEntry } from "../components/ReaderView";
import { api, type ReaderState } from "../lib/api";
import {
  comparisonCode, consultationKey, decode, exportPublic, newKeyPair, openPdf, STORAGE, unseal,
} from "../lib/crypto";
import { openMetadata } from "../lib/documents";
import { documentLine, errorMessage, formatDateTime } from "../lib/format";
import { useSession } from "../lib/session";
import { grantRef, type Watermark } from "../lib/watermark";

const POLL_MS = 1500;
const POLL_TIMEOUT_MS = 3500;
const ENDED: Record<string, string> = {
  revoked: "Acesso encerrado", expired: "Acesso expirado", exhausted: "Acesso encerrado", locked: "Acesso bloqueado",
};

interface SavedRecipient { privateKey: JsonWebKey; publicKey: string }

function savedRecipient(): SavedRecipient | null {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE.recipient) || "null");
  } catch {
    return null;
  }
}

async function recipientPrivateKey(): Promise<CryptoKey> {
  const saved = savedRecipient();
  if (!saved) throw new Error("Os documentos só abrem na aba que pediu o acesso.");
  return crypto.subtle.importKey("jwk", saved.privateKey, { name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
}

/** Opens the data keys re-sealed for this browser and decrypts titles locally. */
async function unlockGrant(state: ReaderState) {
  const shared = await consultationKey(await recipientPrivateKey(), state.sender_key!, state.salt!);
  const keys = new Map<string, Uint8Array<ArrayBuffer>>();
  const entries: ReaderEntry[] = [];
  for (const document of state.documents ?? []) {
    const rawKey = await unseal(shared, decode(document.wrapped_key), "recipient", document.id);
    keys.set(document.id, rawKey);
    const { title, issuer } = await openMetadata(rawKey, document);
    entries.push({ id: document.id, title, subtitle: documentLine({ document_date: document.document_date, issuer }) });
  }
  return { keys, entries };
}

/** "Ler documentos": in-person QR (no handle) or a request to podeabrir.com/@handle. */
export function Reader({ handle }: { handle?: string }) {
  const { session } = useSession();
  const navigate = useNavigate();
  const [reader, setReader] = useState<ReaderState | null>(null);
  const [code, setCode] = useState("");
  const [unlocked, setUnlocked] = useState<{ keys: Map<string, Uint8Array<ArrayBuffer>>; entries: ReaderEntry[] } | null>(null);
  const [handleInput, setHandleInput] = useState("");
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const state = reader?.state;
  const watermark = useMemo<Watermark | null>(() => {
    if (!reader?.grant) return null;
    const origin = reader.channel === "handle" && handle ? `@${handle}` : "leitura presencial";
    return {
      seed: reader.grant,
      lines: [
        "DIVULGAÇÃO PROIBIDA · SOMENTE LEITURA",
        `pode abrir · ${origin} · Ref. ${grantRef(reader.grant)} · ${formatDateTime(new Date().toISOString())}`,
        "Dados pessoais protegidos pela LGPD (Lei 13.709/2018)",
      ],
    };
  }, [reader?.grant, reader?.channel, handle]);

  const show = useCallback(async (next: ReaderState) => {
    if (next.state !== "active" && next.state !== "pending") sessionStorage.removeItem(STORAGE.recipient);
    setUnlocked(null);
    setReader(next);
    if (next.state === "pending" && next.nonce) {
      const saved = savedRecipient();
      setCode(saved ? await comparisonCode(saved.publicKey, next.nonce) : "");
    }
    if (next.state === "active") {
      try {
        setUnlocked(await unlockGrant(next));
      } catch (cause) {
        setError(errorMessage(cause));
      }
    }
  }, []);

  const refresh = useCallback(() => {
    api.reader().then(show, () => setOffline(true));
  }, [show]);

  useEffect(refresh, [refresh]);

  // The server is the source of truth: poll while pending/active and close the reader on any change.
  useEffect(() => {
    if (state !== "pending" && state !== "active") return;
    let timer = 0;
    let stopped = false;
    async function check() {
      try {
        const current = await api.readerStatus(AbortSignal.timeout(POLL_TIMEOUT_MS));
        if (stopped) return;
        if (current === "idle") throw new Error("lost");
        if (current !== state) {
          setUnlocked(null);
          refresh();
          return;
        }
        timer = window.setTimeout(check, POLL_MS);
      } catch {
        if (stopped) return;
        setUnlocked(null);
        setReader(null);
        setOffline(true);
      }
    }
    timer = window.setTimeout(check, POLL_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [state, refresh]);

  useEffect(() => {
    const onShow = (event: PageTransitionEvent) => event.persisted && location.reload();
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);

  const open = useCallback(async (id: string, signal: AbortSignal) => {
    const rawKey = unlocked?.keys.get(id);
    if (!rawKey) throw new Error("Documento indisponível.");
    const { ciphertext } = await api.readerContent(id, signal);
    return openPdf(rawKey, ciphertext, id);
  }, [unlocked]);

  async function requestAccess() {
    setBusy(true);
    setError("");
    try {
      const { publicKey, privateKey } = await newKeyPair();
      const exported = await exportPublic(publicKey);
      sessionStorage.setItem(STORAGE.recipient, JSON.stringify({
        privateKey: await crypto.subtle.exportKey("jwk", privateKey), publicKey: exported,
      }));
      await show(await api.requestReader(exported, handle));
    } catch (cause) {
      sessionStorage.removeItem(STORAGE.recipient);
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  function goToHandle(event: FormEvent) {
    event.preventDefault();
    // Accept "nome", "@nome" or a pasted "podeabrir.com/@nome" link.
    const target = handleInput.trim().split("@").pop()!.replace(/[/?#].*$/, "").toLowerCase();
    if (target) navigate(`/@${target}`);
  }

  if (offline) {
    return <p className="surface empty narrow" role="status">Não foi possível verificar o acesso. Atualize a página para tentar novamente.</p>;
  }
  if (!reader) return null;

  if (state === "active") {
    if (!unlocked || !watermark) return error ? <section className="surface form-card narrow"><Alert message={error} /></section> : null;
    return (
      <ReaderView heading="Documentos compartilhados" entries={unlocked.entries}
        until={new Date(reader.expires_at!).getTime()} open={open} onExpire={refresh} watermark={watermark} />
    );
  }

  if (state === "pending" && reader.channel === "handle") {
    return (
      <section className="surface form-card narrow pairing-card">
        <ShieldCheck className="hero-icon" size={40} aria-hidden="true" />
        <h1>Aguardando aprovação</h1>
        <p className="muted">
          {handle ? <>Peça para <strong>@{handle}</strong> abrir o Pode Abrir no celular.</> : "Peça para a pessoa abrir o Pode Abrir no celular."}
          {" "}A pessoa deve conferir que o código abaixo é o mesmo exibido no celular dela.
        </p>
        <p className="comparison-code" aria-label="Código de conferência">{code.slice(0, 3)} {code.slice(3)}</p>
        <p className="muted" role="status"><span className="pulse" aria-hidden="true" />O pedido vale {session.limits.pair_minutes} minutos.</p>
      </section>
    );
  }

  if (state === "pending") {
    return (
      <section className="surface form-card narrow pairing-card">
        <h1>Aponte a câmera do celular</h1>
        <p className="muted">Quem compartilha escaneia o QR com o celular e escolhe os documentos.</p>
        <img className="qr" src={reader.qr} width={224} height={224} alt="QR para autorizar este computador" />
        <p className="pair-code">{reader.code}</p>
        <p className="muted" role="status">
          <span className="pulse" aria-hidden="true" />Aguardando aprovação. O código vale {session.limits.pair_minutes} minutos.
        </p>
      </section>
    );
  }

  const title = ENDED[state!] ?? (handle ? `Ler documentos de @${handle}` : "Ler documentos");
  return (
    <section className="surface form-card narrow pairing-card">
      {handle ? <AtSign className="hero-icon" size={40} aria-hidden="true" /> : <MonitorSmartphone className="hero-icon" size={40} aria-hidden="true" />}
      <h1>{title}</h1>
      <p className="muted">
        {handle
          ? "A pessoa recebe o pedido no celular e decide o que liberar e por quanto tempo. Nada fica salvo neste computador."
          : "Gere um código para quem vai compartilhar. Os documentos abrem só nesta tela, por tempo limitado."}
      </p>
      <Alert message={error} />
      <div className="actions center">
        <button className="button primary" onClick={requestAccess} disabled={busy}>
          {handle ? "Pedir acesso" : "Gerar código de leitura"}
        </button>
      </div>
      {!handle && (
        <form className="handle-jump" onSubmit={goToHandle}>
          <label htmlFor="handle-input">Tem o endereço da pessoa?</label>
          <div className="copy-row">
            <div className="prefixed">
              <span aria-hidden="true">@</span>
              <input id="handle-input" placeholder="nome" autoCapitalize="none" autoComplete="off" spellCheck={false}
                maxLength={60} value={handleInput} onChange={(event) => setHandleInput(event.target.value)} />
            </div>
            <button className="button secondary">Ir</button>
          </div>
        </form>
      )}
    </section>
  );
}
