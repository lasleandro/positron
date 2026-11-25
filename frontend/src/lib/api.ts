/** Thin client for the Django JSON API ({ data, error } envelope, CSRF header). */

export interface User { email: string; is_staff: boolean }
export interface Limits {
  pdf_max_bytes: number;
  pair_minutes: number;
  access_minutes: number;
  invitation_hours: number;
  in_person_minutes: number[];
  link_minutes: number[];
  extend_minutes: number[];
  max_opens: number;
  link_view_minutes: number;
}
export interface Session { user: User | null; csrf_token: string; vault_namespace: string; limits: Limits }
/** Title and issuer arrive sealed; the browser opens them with the document's data key. */
export interface SealedDocument { id: string; sealed_title: string; sealed_issuer: string; document_date: string }
export interface OwnerDocument extends SealedDocument { wrapped_key: string }
export interface DocumentPage { items: OwnerDocument[]; next_page: number | null }
export type GrantChannel = "in_person" | "link" | "handle";
export type GrantState = "idle" | "pending" | "active" | "expired" | "revoked" | "exhausted" | "locked";
export interface Grant {
  id: string;
  channel: GrantChannel;
  state: GrantState;
  label: string;
  created_at: string;
  expires_at: string | null;
  ended_at: string | null;
  max_opens: number | null;
  opens: number;
  pin: boolean;
  code: string;
  documents: SealedDocument[];
  recipient_key?: string;
  nonce?: string;
  pair_until?: string;
  duplicate?: boolean;
}
export interface GrantEvent {
  id: number;
  grant: string;
  channel: GrantChannel;
  kind: string;
  document: string;
  agent: string;
  detail: string;
  at: string;
  prev_hash: string;
  hash: string;
}
export interface Profile { handle: string | null; handle_active: boolean; address: string; address_qr: string; push_public_key: string }
export interface ReaderState {
  state: GrantState;
  channel: GrantChannel | null;
  code?: string;
  qr?: string;
  nonce?: string;
  pair_until?: string;
  salt?: string;
  sender_key?: string;
  expires_at?: string;
  documents?: (SealedDocument & { wrapped_key: string })[];
}
export interface LinkPreview { state: "available" | "unavailable"; pin_required?: boolean; label?: string; document_count?: number; expires_at?: string }
export interface LinkOpened { label: string; expires_at: string; view_until: number; documents: (SealedDocument & { wrapped_key: string })[] }
export interface ShareBody { documents: string[]; share_keys: Record<string, string> }
export interface AuthenticatorSetup { email: string; qr: string; secret: string }
export interface OwnerSession extends Session { wrapped_vault: string }
export interface AccountKeys { wrapped_password: string; wrapped_recovery: string; recovery_proof: string }
export interface ResetConfirmation {
  token: string;
  otp: string;
  mode: "recovery" | "fresh";
  password: string;
  wrapped_password: string;
  recovery_proof: string;
  wrapped_recovery?: string;
}
export interface SealedFile { ciphertext: Uint8Array<ArrayBuffer>; wrappedKey: string }

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

let csrfToken = "";

export function rememberCsrf(session: Session) {
  csrfToken = session.csrf_token;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch("/api/" + path, { method, headers, body: payload, cache: "no-store" });
  if (response.status === 204) return undefined as T;
  const envelope = await response.json().catch(() => null);
  if (!response.ok || !envelope || envelope.error) {
    const error = envelope?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "unexpected",
      error?.message ?? "Não foi possível concluir a operação.",
      error?.fields,
    );
  }
  return envelope.data as T;
}

/** Fetch an encrypted document: ciphertext body plus its wrapped data key header. */
async function sealedFile(path: string, signal?: AbortSignal): Promise<SealedFile> {
  const response = await fetch("/api/" + path, { signal, cache: "no-store" });
  const wrappedKey = response.headers.get("X-Document-Key");
  if (!response.ok || !wrappedKey) throw new ApiError(response.status, "unavailable", "Acesso ao documento indisponível.");
  return { ciphertext: new Uint8Array(await response.arrayBuffer()), wrappedKey };
}

const withSession = async (promise: Promise<Session>) => {
  const session = await promise;
  rememberCsrf(session);
  return session;
};

export const api = {
  session: () => withSession(request<Session>("GET", "session/")),
  login: (email: string, password: string, otp: string) =>
    withSession(request<OwnerSession>("POST", "auth/login/", { email, password, otp })) as Promise<OwnerSession>,
  logout: () => withSession(request<Session>("POST", "auth/logout/")),
  verifyVault: (password: string) => request<{ wrapped_vault: string }>("POST", "auth/vault/verify/", { password }),
  requestPasswordReset: (email: string) => request<{ message: string }>("POST", "auth/password-reset/", { email }),
  inspectReset: (token: string) =>
    request<{ email: string; wrapped_recovery: string }>("POST", "auth/password-reset/inspect/", { token }),
  confirmReset: (payload: ResetConfirmation) => request<{ mode: string }>("POST", "auth/password-reset/confirm/", payload),

  inspectInvitation: (token: string) => request<{ email: string }>("POST", "invitations/inspect/", { token }),
  bootstrapInvitation: (token: string, email: string) =>
    request<{ email: string }>("POST", "invitations/bootstrap/", { token, email }),
  createInvitation: (email: string) => request<{ email: string }>("POST", "invitations/", { email }),
  enroll: (token: string, password: string, keys: AccountKeys) =>
    request<AuthenticatorSetup>("POST", "enrollment/", { token, password, ...keys }),
  confirmEnrollment: (otp: string) =>
    withSession(request<OwnerSession>("POST", "enrollment/confirm/", { otp })) as Promise<OwnerSession>,

  documents: (page = 1) => request<DocumentPage>("GET", `documents/?page=${page}`),
  document: (id: string) => request<OwnerDocument>("GET", `documents/${id}/`),
  uploadDocument: (form: FormData) => request<OwnerDocument>("POST", "documents/", form),
  documentContent: (id: string, signal?: AbortSignal) => sealedFile(`documents/${id}/content/`, signal),
  deleteDocument: (id: string) => request<void>("DELETE", `documents/${id}/`),

  grants: () => request<Grant[]>("GET", "grants/"),
  pendingRequests: () => request<{ count: number; items: { id: string; pair_until: string }[] }>("GET", "grants/pending/"),
  pairingKey: (shortCode: string) =>
    request<{ recipient_key: string }>("GET", `pairings/${encodeURIComponent(shortCode)}/key/`),
  approveInPerson: (body: ShareBody & { code: string; sender_key: string; minutes: number }) =>
    request<Grant>("POST", "grants/in-person/", body),
  approveRequest: (id: string, body: ShareBody & { sender_key: string; minutes: number }) =>
    request<Grant>("POST", `grants/${id}/approve/`, body),
  createLink: (body: ShareBody & { minutes: number; max_opens: number | null; pin: string; label: string }) =>
    request<Grant>("POST", "grants/links/", body),
  extendGrant: (id: string, minutes: number) => request<Grant>("POST", `grants/${id}/extend/`, { minutes }),
  revokeGrant: (id: string) => request<void>("DELETE", `grants/${id}/`),

  profile: () => request<Profile>("GET", "profile/"),
  updateProfile: (handle: string, active: boolean) => request<Profile>("PUT", "profile/", { handle, active }),
  subscribePush: (subscription: { endpoint: string; p256dh: string; auth: string }) =>
    request<void>("POST", "profile/push/", subscription),
  unsubscribePush: (endpoint: string) => request<void>("DELETE", "profile/push/", { endpoint }),
  history: () => request<{ events: GrantEvent[]; total: number }>("GET", "history/"),

  reader: () => request<ReaderState>("GET", "reader/"),
  requestReader: (recipientKey: string, handle?: string) =>
    request<ReaderState>("POST", "reader/", handle ? { recipient_key: recipientKey, handle } : { recipient_key: recipientKey }),
  readerStatus: (signal?: AbortSignal) => pollState("reader/status/", signal),
  readerContent: (id: string, signal?: AbortSignal) => sealedFile(`reader/documents/${id}/content/`, signal),

  linkPreview: (id: string) => request<LinkPreview>("GET", `links/${id}/`),
  openLink: (id: string, pin: string) => request<LinkOpened>("POST", `links/${id}/open/`, pin ? { pin } : {}),
  linkStatus: (id: string, signal?: AbortSignal) => pollState(`links/${id}/status/`, signal),
  linkContent: (id: string, documentId: string, signal?: AbortSignal) =>
    sealedFile(`links/${id}/documents/${documentId}/content/`, signal),
};

/** Lightweight polling call: rejects on any failure so callers fail closed. */
function pollState(path: string, signal?: AbortSignal): Promise<string> {
  return fetch("/api/" + path, { cache: "no-store", signal })
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error("status"))))
    .then((envelope) => envelope.data.state as string);
}

/** Load every page (search and sharing work on the whole, locally decrypted library). */
export async function allDocuments(): Promise<OwnerDocument[]> {
  const items: OwnerDocument[] = [];
  for (let page: number | null = 1; page !== null;) {
    const result: DocumentPage = await api.documents(page);
    items.push(...result.items);
    page = result.next_page;
  }
  return items;
}
