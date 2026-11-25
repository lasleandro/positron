import { FileLock2, Lock, TimerOff } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router";

import { Alert } from "../components/Alert";
import { ReaderView, type ReaderEntry } from "../components/ReaderView";
import { api, type LinkOpened, type LinkPreview } from "../lib/api";
import { aesKey, decode, openPdf, unseal } from "../lib/crypto";
import { openMetadata } from "../lib/documents";
import { documentLine, errorMessage, formatDateTime, formatDuration } from "../lib/format";
import { useSession } from "../lib/session";

const POLL_MS = 3000;
const KEY_PATTERN = /^[A-Za-z0-9_-]{43}$/;

/** The link key lives in the URL fragment (never sent to the server). Keep it for this tab only
 * and strip it from the address bar so it does not linger in screenshots or shared screens. */
function takeLinkKey(id: string): string {
  const slot = `podeabrir:link:${id}`;
  const fragment = location.hash.slice(1);
  if (KEY_PATTERN.test(fragment)) {
    sessionStorage.setItem(slot, fragment);
    history.replaceState(history.state, "", location.pathname);
    return fragment;
  }
  const saved = sessionStorage.getItem(slot) ?? "";
  return KEY_PATTERN.test(saved) ? saved : "";
}

async function unlockLink(linkKey: string, opened: LinkOpened) {
  const key = await aesKey(decode(linkKey));
  const keys = new Map<string, Uint8Array<ArrayBuffer>>();
  const entries: ReaderEntry[] = [];
  for (const document of opened.documents) {
    const rawKey = await unseal(key, decode(document.wrapped_key), "link", document.id);
    keys.set(document.id, rawKey);
    const { title, issuer } = await openMetadata(rawKey, document);
    entries.push({ id: document.id, title, subtitle: documentLine({ document_date: document.document_date, issuer }) });
  }
  return { keys, entries };
}

export function LinkReader() {
  const { session } = useSession();
  const { linkId = "" } = useParams();
  const [linkKey] = useState(() => takeLinkKey(linkId));
  const [preview, setPreview] = useState<LinkPreview | null>(null);
  const [pin, setPin] = useState("");
  const [opened, setOpened] = useState<{ until: number; label: string; keys: Map<string, Uint8Array<ArrayBuffer>>; entries: ReaderEntry[] } | null>(null);
  const [ended, setEnded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.linkPreview(linkId).then(setPreview, () => setPreview({ state: "unavailable" }));
  }, [linkId]);

  const close = useCallback(() => {
    setOpened(null);
    setEnded(true);
  }, []);

  // Revocation or expiry on the server closes the reader within seconds.
  useEffect(() => {
    if (!opened) return;
    let timer = 0;
    let stopped = false;
    async function check() {
      const state = await api.linkStatus(linkId, AbortSignal.timeout(POLL_MS)).catch(() => "ended");
      if (stopped) return;
      if (state !== "active") return close();
      timer = window.setTimeout(check, POLL_MS);
    }
    timer = window.setTimeout(check, POLL_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [opened, linkId, close]);

  const openDocument = useCallback(async (id: string, signal: AbortSignal) => {
    const rawKey = opened?.keys.get(id);
    if (!rawKey) throw new Error("Documento indisponível.");
    const { ciphertext } = await api.linkContent(linkId, id, signal);
    return openPdf(rawKey, ciphertext, id);
  }, [opened, linkId]);

  async function openLink(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.openLink(linkId, pin);
      const unlocked = await unlockLink(linkKey, result);
      const until = Math.min(new Date(result.expires_at).getTime(), result.view_until * 1000);
      setOpened({ until, label: result.label, ...unlocked });
    } catch (cause) {
      setError(cause instanceof Error && cause.name === "OperationError"
        ? "O link está incompleto. Peça para a pessoa enviar o link inteiro novamente."
        : errorMessage(cause));
    } finally {
      setPin("");
      setBusy(false);
    }
  }

  if (opened) {
    return (
      <ReaderView heading="Documentos compartilhados com você" entries={opened.entries} until={opened.until}
        open={openDocument} onExpire={close}
        watermark={`Pode Abrir · ${opened.label || "link"} · ${formatDateTime(new Date().toISOString())}`} />
    );
  }
  if (!preview) return null;
  if (ended || preview.state === "unavailable" || !linkKey) {
    return (
      <section className="surface form-card narrow pairing-card">
        <TimerOff className="hero-icon" size={40} aria-hidden="true" />
        <h1>{ended ? "Leitura encerrada" : "Link indisponível"}</h1>
        <p className="muted">
          {!linkKey && !ended
            ? "O link está incompleto. Peça para a pessoa enviar o link inteiro novamente."
            : "Este link expirou, foi encerrado por quem compartilhou ou já atingiu o limite de aberturas."}
        </p>
      </section>
    );
  }
  return (
    <section className="surface form-card narrow pairing-card">
      <FileLock2 className="hero-icon" size={40} aria-hidden="true" />
      <h1>Alguém compartilhou documentos com você</h1>
      <p className="muted">
        {preview.document_count} documento(s){preview.label ? ` para ${preview.label}` : ""}. Eles são decifrados apenas
        neste navegador. Ao abrir, você terá até {formatDuration(session.limits.link_view_minutes)} de leitura.
      </p>
      <form className="form-grid" onSubmit={openLink}>
        {preview.pin_required && (
          <div>
            <label htmlFor="pin"><Lock size={14} aria-hidden="true" /> PIN informado por quem compartilhou</label>
            <input id="pin" className="mono center" inputMode="numeric" autoComplete="off" pattern="[0-9]{4,8}" maxLength={8} required
              value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))} />
          </div>
        )}
        <Alert message={error} />
        <button className="button primary" disabled={busy}>Abrir documentos</button>
      </form>
    </section>
  );
}
