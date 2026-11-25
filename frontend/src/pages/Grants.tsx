import { AtSign, BellRing, Eye, Link2, MonitorSmartphone, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";

import { Alert } from "../components/Alert";
import { Countdown } from "../components/Countdown";
import { api, type Grant, type GrantChannel, type GrantEvent } from "../lib/api";
import { sha256Hex } from "../lib/crypto";
import { useDocuments } from "../lib/documents";
import { errorMessage, formatDateTime, formatDuration } from "../lib/format";
import { useSession } from "../lib/session";

const POLL_MS = 5000;
const CHANNEL: Record<GrantChannel, { label: string; icon: typeof Link2 }> = {
  in_person: { label: "Leitura presencial", icon: MonitorSmartphone },
  link: { label: "Link", icon: Link2 },
  handle: { label: "Endereço pessoal", icon: AtSign },
};
const EVENT_TEXT: Record<string, string> = {
  requested: "Pedido de leitura recebido", approved: "Acesso liberado", created: "Link criado",
  opened: "Aberto", viewed: "Documento visualizado", denied: "Tentativa negada", extended: "Prazo estendido",
  ended: "Encerrado",
};
const GENESIS = "0".repeat(64);

type Integrity = "checking" | "ok" | "changed" | "broken";

/** Re-hash the chain here; remember the newest link to detect rewrites between visits. */
async function verifyHistory(events: GrantEvent[], email: string): Promise<Integrity> {
  for (let index = 0; index < events.length; index++) {
    const event = events[index];
    if (index > 0 && event.prev_hash !== events[index - 1].hash) return "broken";
    if (index === 0 && events.length && event.id === 1 && event.prev_hash !== GENESIS) return "broken";
    const material = [event.prev_hash, event.at, event.channel, event.kind, event.grant, event.document, event.agent, event.detail].join("|");
    if (await sha256Hex(material) !== event.hash) return "broken";
  }
  const slot = `podeabrir:history:${email}`;
  let verdict: Integrity = "ok";
  try {
    const remembered = JSON.parse(localStorage.getItem(slot) || "null") as { id: number; hash: string } | null;
    const last = events[events.length - 1];
    if (remembered && last) {
      const same = events.find((event) => event.id === remembered.id);
      if ((same && same.hash !== remembered.hash) || remembered.id > last.id) verdict = "changed";
    }
    if (last && verdict === "ok") localStorage.setItem(slot, JSON.stringify({ id: last.id, hash: last.hash }));
  } catch {
    // Storage unavailable (private mode): the chain check above still applies.
  }
  return verdict;
}

export function Grants() {
  const { session } = useSession();
  const { documents } = useDocuments();
  const [grants, setGrants] = useState<Grant[] | null>(null);
  const [events, setEvents] = useState<GrantEvent[]>([]);
  const [integrity, setIntegrity] = useState<Integrity>("checking");
  const [error, setError] = useState("");
  const titles = new Map(documents.map((doc) => [doc.id, doc.title]));
  const email = session.user?.email ?? "";

  const load = useCallback(() => {
    api.grants().then(setGrants, (cause) => setError(errorMessage(cause)));
    api.history().then(async ({ events: chain }) => {
      setEvents(chain);
      setIntegrity(await verifyHistory(chain, email));
    }, () => {});
  }, [email]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  function end(grant: Grant) {
    // Optimistic: moves to "encerrados" at once; restored if the server refuses.
    setError("");
    setGrants((list) => list?.map((item) => (item.id === grant.id ? { ...item, state: "revoked", ended_at: new Date().toISOString() } : item)) ?? null);
    api.revokeGrant(grant.id).catch((cause) => {
      setGrants((list) => list?.map((item) => (item.id === grant.id ? grant : item)) ?? null);
      setError(errorMessage(cause, "Não foi possível encerrar. Tente novamente."));
    });
  }

  function extend(grant: Grant, minutes: number) {
    setError("");
    api.extendGrant(grant.id, minutes).then(
      (updated) => setGrants((list) => list?.map((item) => (item.id === grant.id ? updated : item)) ?? null),
      (cause) => setError(errorMessage(cause)),
    );
  }

  const pending = grants?.filter((grant) => grant.state === "pending") ?? [];
  const active = grants?.filter((grant) => grant.state === "active") ?? [];
  const ended = grants?.filter((grant) => !["pending", "active"].includes(grant.state)) ?? [];
  const docNames = (grant: Grant) => grant.documents.map((doc) => titles.get(doc.id) ?? "Documento").join(", ");

  return (
    <div className="narrow wide-ish">
      <div className="page-heading">
        <div><h1>Compartilhamentos</h1><p className="muted">Quem pode abrir o quê, por quanto tempo. Encerre quando quiser.</p></div>
        <div className="actions tight">
          <Link className="button secondary" to="/autorizar/">Leitura presencial</Link>
          <Link className="button primary" to="/compartilhar/"><Link2 size={16} aria-hidden="true" />Novo link</Link>
        </div>
      </div>
      <Alert message={error} />

      {pending.length > 0 && (
        <section className="grant-section">
          <h2><BellRing size={18} aria-hidden="true" />Pedidos de leitura</h2>
          {pending.map((grant) => (
            <article key={grant.id} className="surface grant-card request">
              <div className="grant-meta">
                <strong>Alguém pediu para ler seus documentos</strong>
                {grant.pair_until && <Countdown until={new Date(grant.pair_until).getTime()} prefix="Expira em" />}
              </div>
              <div className="actions tight">
                <Link className="button primary" to={`/autorizar/pedido/${grant.id}`}>Conferir código e aprovar</Link>
                <button className="button ghost" onClick={() => end(grant)}>Recusar</button>
              </div>
            </article>
          ))}
        </section>
      )}

      <section className="grant-section">
        <h2>Ativos</h2>
        {grants && active.length === 0 && <p className="surface empty">Nada compartilhado agora.</p>}
        {active.map((grant) => {
          const { label, icon: Icon } = CHANNEL[grant.channel];
          return (
            <article key={grant.id} className="surface grant-card">
              <div className="grant-meta">
                <span className="channel"><Icon size={16} aria-hidden="true" />{label}{grant.label ? ` · ${grant.label}` : ""}</span>
                {grant.expires_at && <Countdown until={new Date(grant.expires_at).getTime()} prefix="Termina em" />}
              </div>
              <p className="grant-docs">{docNames(grant)}</p>
              <p className="grant-policy">
                {grant.channel === "link" && (grant.max_opens ? `Aberto ${grant.opens} de ${grant.max_opens}` : `Aberto ${grant.opens} vez(es)`)}
                {grant.pin && " · com PIN"}
              </p>
              <div className="actions tight">
                {session.limits.extend_minutes.map((minutes) => (
                  <button key={minutes} className="button ghost" onClick={() => extend(grant, minutes)}>+{formatDuration(minutes)}</button>
                ))}
                <button className="button danger" onClick={() => end(grant)}><XCircle size={16} aria-hidden="true" />Encerrar</button>
              </div>
            </article>
          );
        })}
      </section>

      {ended.length > 0 && (
        <section className="grant-section">
          <h2>Encerrados recentemente</h2>
          <ul className="ended-list">
            {ended.map((grant) => (
              <li key={grant.id}>
                <span>{CHANNEL[grant.channel].label}{grant.label ? ` · ${grant.label}` : ""}</span>
                <small>{grant.documents.length ? `${docNames(grant)} · ` : ""}{grant.state === "locked" ? "bloqueado (PIN)" : grant.state === "exhausted" ? "limite atingido" : grant.state === "expired" ? "expirou" : "encerrado"}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="grant-section">
        <h2><Eye size={18} aria-hidden="true" />Quem viu</h2>
        <p className={`integrity ${integrity}`}>
          {integrity === "broken" || integrity === "changed" ? <ShieldAlert size={16} aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
          {integrity === "ok" && "Histórico íntegro: cada registro está encadeado ao anterior e foi conferido neste navegador."}
          {integrity === "checking" && "Conferindo o histórico…"}
          {integrity === "changed" && "Atenção: o histórico mudou desde a sua última visita."}
          {integrity === "broken" && "Atenção: o encadeamento do histórico não confere."}
        </p>
        {events.length === 0 ? <p className="surface empty">Nenhum registro ainda.</p> : (
          <ul className="history surface">
            {[...events].reverse().map((event) => (
              <li key={event.id}>
                <span className="history-when">{formatDateTime(event.at)}</span>
                <span>
                  <strong>{EVENT_TEXT[event.kind] ?? event.kind}</strong>
                  {event.document && ` · ${titles.get(event.document) ?? "documento"}`}
                  <small> {CHANNEL[event.channel]?.label}{event.agent ? ` · ${event.agent}` : ""}{event.detail ? ` · ${event.detail}` : ""}</small>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
