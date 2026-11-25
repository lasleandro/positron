import { Inbox, Send, ShieldCheck, UsersRound } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import { Alert } from "../components/Alert";
import {
  api, type AdminAccessRequest, type AdminInvitation, type AdminUser, type ApiError, type InvitationStatus, type Page,
} from "../lib/api";
import { errorMessage, formatDateTime } from "../lib/format";
import { useSession } from "../lib/session";

const TABS = [
  { id: "convites", label: "Convites", icon: Send },
  { id: "solicitacoes", label: "Solicitações", icon: Inbox },
  { id: "pessoas", label: "Pessoas", icon: UsersRound },
] as const;
type TabId = (typeof TABS)[number]["id"];

const INVITE_STATUS: Record<InvitationStatus, string> = {
  queued: "Na fila", sent: "Enviado", bounced: "Não entregue", failed: "Falhou", expired: "Expirou", account: "Conta criada",
};
const BOUNCE_WATCH_MS = 5 * 60 * 1000;

/** Plain-language reason for an enhanced status code (RFC 3463) from a bounce report. */
function bounceReason(code: string): string {
  if (/^5\.1\.(0|1|10)$/.test(code)) return "endereço não existe";
  if (code === "5.2.2") return "caixa de entrada cheia";
  if (code === "5.2.1") return "caixa desativada";
  return "recusado pelo servidor do destinatário";
}
const REQUEST_STATUS: Record<AdminAccessRequest["status"], string> = { new: "Nova", invited: "Convidada", account: "Já tem conta" };
const POLL_MS = 5000;

/** One paged admin list: first page on mount, "Carregar mais" appends, items editable for optimistic updates. */
function usePaged<T>(fetchPage: (page: number) => Promise<Page<T>>) {
  const [items, setItems] = useState<T[] | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    fetchPage(1).then((result) => { setItems(result.items); setPage(1); setHasMore(result.has_more); },
      (cause) => setError(errorMessage(cause)));
  }, [fetchPage]);
  useEffect(reload, [reload]);

  function loadMore() {
    fetchPage(page + 1).then((result) => {
      setItems((list) => [...(list ?? []), ...result.items]);
      setPage(page + 1);
      setHasMore(result.has_more);
    }, (cause) => setError(errorMessage(cause)));
  }
  return { items, setItems, hasMore, loadMore, reload, error, setError };
}

function MoreButton({ visible, onClick }: { visible: boolean; onClick: () => void }) {
  return visible ? <button type="button" className="button ghost load-more" onClick={onClick}>Carregar mais</button> : null;
}

function Invitations() {
  const { session } = useSession();
  const list = usePaged(api.adminInvitations);
  const { items, setItems, setError, reload } = list;
  const [email, setEmail] = useState("");
  const [admin, setAdmin] = useState(false);

  // Follow the outbox until sent or failed, and recent sends a few minutes more: bounces arrive later.
  const waiting = items?.some((item) => item.status === "queued"
    || (item.status === "sent" && Date.now() - Date.parse(item.created_at) < BOUNCE_WATCH_MS));
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting, reload]);

  function send(target: string, asAdmin: boolean) {
    // Optimistic: listed as queued at once; marked as failed if the server refuses.
    const temporary: AdminInvitation = {
      id: `new-${Date.now()}`, email: target, admin: asAdmin, created_at: new Date().toISOString(), status: "queued", bounce_code: "",
    };
    setError("");
    setItems((current) => [temporary, ...(current ?? [])]);
    api.createInvitation(target, asAdmin).then(reload, (cause: ApiError) => {
      setItems((current) => current?.filter((item) => item.id !== temporary.id) ?? null);
      setError(`${target}: ${errorMessage(cause)}`);
    });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(email.trim().toLowerCase(), admin);
    setEmail("");
    setAdmin(false);
  }

  return (
    <>
      <form className="surface admin-invite" onSubmit={submit}>
        <label htmlFor="invite-email">Email da pessoa convidada</label>
        <div className="copy-row">
          <input id="invite-email" type="email" maxLength={150} required autoComplete="off"
            value={email} onChange={(event) => setEmail(event.target.value)} />
          <button className="button primary"><Send size={16} aria-hidden="true" />Enviar convite</button>
        </div>
        <label className="choice">
          <input type="checkbox" checked={admin} onChange={(event) => setAdmin(event.target.checked)} />
          <span>Administrador: poderá convidar pessoas e gerenciar acessos</span>
        </label>
        <p className="muted small">O convite vale uma vez e expira em {session.limits.invitation_hours} horas. A conta fica vinculada a esse email.</p>
      </form>
      <Alert message={list.error} />
      {items && items.length === 0 && <p className="surface empty">Nenhum convite enviado ainda.</p>}
      {items && items.length > 0 && (
        <ul className="admin-list surface">
          {items.map((item) => (
            <li key={item.id}>
              <span className="admin-main">
                <strong>{item.email}</strong>
                <small>{item.admin ? "Administrador · " : ""}enviado {formatDateTime(item.created_at)}</small>
                {item.status === "bounced" && <small className="admin-bounce">Não entregue: {bounceReason(item.bounce_code)}. Confira o endereço e convide de novo.</small>}
              </span>
              <span className="admin-side">
                <span className={`status-badge ${item.status}`}>{INVITE_STATUS[item.status]}</span>
                {(item.status === "failed" || item.status === "expired") && (
                  <button type="button" className="button ghost" onClick={() => send(item.email, item.admin)}>Reenviar</button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <MoreButton visible={list.hasMore} onClick={list.loadMore} />
    </>
  );
}

function AccessRequests() {
  const list = usePaged(api.adminAccessRequests);
  const { items, setItems, setError } = list;

  function invite(request: AdminAccessRequest) {
    // Optimistic: every request from that address shows as invited; restored if the server refuses.
    const mark = (status: AdminAccessRequest["status"]) => (item: AdminAccessRequest) => (item.email === request.email ? { ...item, status } : item);
    setError("");
    setItems((current) => current?.map(mark("invited")) ?? null);
    api.createInvitation(request.email).catch((cause: ApiError) => {
      setItems((current) => current?.map(mark(cause.code === "username_taken" ? "account" : request.status)) ?? null);
      if (cause.code !== "username_taken") setError(`${request.email}: ${errorMessage(cause)}`);
    });
  }

  return (
    <>
      <Alert message={list.error} />
      {items && items.length === 0 && <p className="surface empty">Nenhuma solicitação recebida.</p>}
      {items && items.length > 0 && (
        <ul className="admin-list surface">
          {items.map((item) => (
            <li key={item.id}>
              <span className="admin-main">
                <strong>{item.name || item.email}</strong>
                <small>{item.name ? `${item.email} · ` : ""}{formatDateTime(item.created_at)}</small>
                {item.message && <span className="admin-message">{item.message}</span>}
              </span>
              <span className="admin-side">
                <span className={`status-badge ${item.status}`}>{REQUEST_STATUS[item.status]}</span>
                {item.status === "new" && (
                  <button type="button" className="button secondary" onClick={() => invite(item)}><Send size={15} aria-hidden="true" />Convidar</button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <MoreButton visible={list.hasMore} onClick={list.loadMore} />
    </>
  );
}

function People() {
  const list = usePaged(api.adminUsers);
  const { items, setItems, setError } = list;

  function toggle(user: AdminUser) {
    // Optimistic: flips at once; flips back if the server refuses.
    const set = (isStaff: boolean) => setItems((current) => current?.map((item) => (item.id === user.id ? { ...item, is_staff: isStaff } : item)) ?? null);
    setError("");
    set(!user.is_staff);
    api.setAdmin(user.id, !user.is_staff).catch((cause) => {
      set(user.is_staff);
      setError(`${user.email}: ${errorMessage(cause)}`);
    });
  }

  return (
    <>
      <Alert message={list.error} />
      {items && (
        <ul className="admin-list surface">
          {items.map((user) => (
            <li key={user.id}>
              <span className="admin-main">
                <strong>{user.email}{user.is_self && <small className="you"> (você)</small>}</strong>
                <small>entrou {formatDateTime(user.date_joined)} · {user.last_login ? `último acesso ${formatDateTime(user.last_login)}` : "nunca acessou"}</small>
              </span>
              <span className="admin-side">
                <label className="switch" title={user.is_self ? "Você não pode alterar o seu próprio acesso" : undefined}>
                  <input type="checkbox" checked={user.is_staff} disabled={user.is_self} onChange={() => toggle(user)} />
                  <span>Administrador</span>
                </label>
              </span>
            </li>
          ))}
        </ul>
      )}
      <MoreButton visible={list.hasMore} onClick={list.loadMore} />
    </>
  );
}

export function Admin() {
  const [params, setParams] = useSearchParams();
  const tab: TabId = TABS.some((item) => item.id === params.get("aba")) ? (params.get("aba") as TabId) : "convites";

  return (
    <div className="narrow wide-ish">
      <div className="page-heading">
        <div>
          <h1><ShieldCheck size={26} aria-hidden="true" /> Administração</h1>
          <p className="muted">Convites, solicitações de acesso e quem administra a plataforma.</p>
        </div>
      </div>
      <div className="segmented admin-tabs" role="tablist" aria-label="Seções da administração">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "segment on" : "segment"}
            onClick={() => setParams({ aba: id }, { replace: true })}>
            <Icon size={16} aria-hidden="true" />{label}
          </button>
        ))}
      </div>
      <section className="admin-panel" role="tabpanel" aria-label={TABS.find((item) => item.id === tab)?.label}>
        {tab === "convites" && <Invitations />}
        {tab === "solicitacoes" && <AccessRequests />}
        {tab === "pessoas" && <People />}
      </section>
    </div>
  );
}
