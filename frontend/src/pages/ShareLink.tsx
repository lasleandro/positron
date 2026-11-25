import { Check, Copy, KeyRound, Link2, Share2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";

import { Alert } from "../components/Alert";
import { DocumentPicker } from "../components/DocumentPicker";
import { DurationSelect } from "../components/DurationSelect";
import { api } from "../lib/api";
import { aesKey, decode, encode, newLinkKey, seal, unseal } from "../lib/crypto";
import { shareable, useDocuments } from "../lib/documents";
import { errorMessage, formatDuration } from "../lib/format";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";

type Opens = "once" | "limited" | "unlimited";
const DAY = 24 * 60;

export function ShareLink() {
  const { session } = useSession();
  const { withVault } = useVault();
  const { documents } = useDocuments();
  const available = shareable(documents);
  const route = useLocation();
  // Rows selected in the library arrive preselected (multi-select there, no picking twice).
  const [chosen, setChosen] = useState<Set<string>>(
    () => new Set((route.state as { documents?: string[] } | null)?.documents ?? []),
  );
  const [minutes, setMinutes] = useState(DAY);
  const [opens, setOpens] = useState<Opens>("once");
  const [maxOpens, setMaxOpens] = useState(3);
  const [pin, setPin] = useState("");
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pinRequired = minutes > DAY || chosen.size > 1;

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!chosen.size) return setError("Selecione pelo menos um documento.");
    setBusy(true);
    try {
      const linkKey = newLinkKey();
      const key = await aesKey(decode(linkKey));
      const selected = available.filter((doc) => chosen.has(doc.id));
      const shareKeys = await withVault((vault) => Promise.all(selected.map(async (doc) => {
        const dataKey = await unseal(vault, decode(doc.wrapped_key), "owner", doc.id);
        return [doc.id, encode(await seal(key, dataKey, "link", doc.id))] as const;
      })));
      const grant = await api.createLink({
        documents: selected.map((doc) => doc.id), share_keys: Object.fromEntries(shareKeys), minutes,
        max_opens: opens === "once" ? 1 : opens === "limited" ? maxOpens : null, pin, label: label.trim(),
      });
      setUrl(`${location.origin}/s/${grant.id}#${linkKey}`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
  }

  async function share() {
    await navigator.share({ title: "Documentos no Pode Abrir", url }).catch(() => {});
  }

  if (url) {
    return (
      <section className="surface form-card narrow">
        <h1>Link pronto</h1>
        <p className="muted">
          Envie agora. Por segurança, o link completo contém a chave e <strong>não fica salvo</strong> em lugar nenhum:
          se perder, encerre-o e crie outro.
        </p>
        <div className="form-grid">
          <input className="mono" readOnly value={url} aria-label="Link de compartilhamento" onFocus={(event) => event.target.select()} />
          <div className="actions tight">
            <button type="button" className="button primary" onClick={copy}>
              {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}{copied ? "Copiado" : "Copiar link"}
            </button>
            {"share" in navigator && (
              <button type="button" className="button secondary" onClick={share}><Share2 size={16} aria-hidden="true" />Enviar…</button>
            )}
          </div>
          {pin && <p className="note"><KeyRound size={14} aria-hidden="true" />Envie o PIN por outro canal (ligação, outra conversa).</p>}
          <Link to="/compartilhamentos/">Acompanhar aberturas e encerrar</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="surface form-card narrow">
      <h1><Link2 size={22} aria-hidden="true" /> Compartilhar por link</h1>
      <p className="muted">Quem receber o link lê os documentos no navegador, sem conta e sem baixar. Você vê cada abertura e pode encerrar quando quiser.</p>
      {available.length === 0 ? <p><Link to="/enviar/">Adicione um documento</Link> para compartilhar.</p> : (
        <form className="form-grid" onSubmit={create}>
          <DocumentPicker documents={available} chosen={chosen} onChange={setChosen} legend="Documentos" />
          <DurationSelect id="link-duration" label="Válido por" options={session.limits.link_minutes} value={minutes} onChange={setMinutes} />
          <div role="radiogroup" aria-labelledby="opens-label">
            <span id="opens-label" className="field-label">Aberturas</span>
            <div className="segmented">
              {([["once", "Uma vez"], ["limited", "Algumas vezes"], ["unlimited", "Sem limite"]] as const).map(([value, text]) => (
                <button key={value} type="button" role="radio" aria-checked={opens === value}
                  className={opens === value ? "segment on" : "segment"} onClick={() => setOpens(value)}>{text}</button>
              ))}
            </div>
            {opens === "once" && <small>Como um snap: depois da primeira abertura o link deixa de funcionar.</small>}
            {opens === "limited" && (
              <input aria-label="Número de aberturas" type="number" min={2} max={session.limits.max_opens}
                value={maxOpens} onChange={(event) => setMaxOpens(Number(event.target.value))} />
            )}
            {opens === "unlimited" && <small>Abre quantas vezes quiser até expirar em {formatDuration(minutes)}.</small>}
          </div>
          <div>
            <label htmlFor="pin">PIN {pinRequired ? "(obrigatório para vários documentos ou mais de 24 h)" : "(opcional)"}</label>
            <input id="pin" className="mono" inputMode="numeric" pattern="[0-9]{4,8}" maxLength={8} autoComplete="off"
              required={pinRequired} placeholder="4 a 8 dígitos" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))} />
          </div>
          <div>
            <label htmlFor="label">Para quem (opcional)</label>
            <input id="label" maxLength={80} placeholder="Ex.: Dra. Ana, RH da empresa" value={label} onChange={(event) => setLabel(event.target.value)} />
            <small>Aparece para você na lista e como marca d’água para quem abrir.</small>
          </div>
          <Alert message={error} />
          <button className="button primary" disabled={busy}>Criar link</button>
        </form>
      )}
    </section>
  );
}
