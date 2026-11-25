import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { allDocuments, api, type OwnerDocument, type SealedDocument } from "./api";
import { decode, openText, unseal } from "./crypto";
import { errorMessage } from "./format";
import { useSession } from "./session";
import { useVault } from "./vault";

/** A document as the owner sees it: metadata opened locally, never sent back in clear. */
export interface PlainDocument {
  id: string;
  title: string;
  issuer: string;
  document_date: string;
  wrapped_key: string;
  status?: "sending" | "failed";
  error?: string;
}

/** Open title/issuer with an already-unwrapped data key (owner or grantee). */
export async function openMetadata(rawKey: Uint8Array<ArrayBuffer>, document: SealedDocument) {
  const [title, issuer] = await Promise.all([
    openText(rawKey, document.sealed_title, "meta-title", document.id),
    openText(rawKey, document.sealed_issuer, "meta-issuer", document.id),
  ]);
  return { title, issuer };
}

async function decryptOwned(vault: CryptoKey, documents: OwnerDocument[]): Promise<PlainDocument[]> {
  return Promise.all(documents.map(async (document) => {
    const rawKey = await unseal(vault, decode(document.wrapped_key), "owner", document.id);
    return { ...(await openMetadata(rawKey, document)), id: document.id, document_date: document.document_date, wrapped_key: document.wrapped_key };
  }));
}

interface DocumentsContextValue {
  documents: PlainDocument[];
  loaded: boolean;
  error: string;
  reload: () => void;
  ensureLoaded: () => void;
  submitUpload: (draft: Omit<PlainDocument, "status">, form: FormData) => void;
  dismiss: (id: string) => void;
  /** Optimistic delete: rows vanish at once and come back if the server refuses. */
  remove: (ids: string[]) => Promise<void>;
}

const DocumentsContext = createContext<DocumentsContextValue | null>(null);

export function DocumentsProvider({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const { withVault } = useVault();
  const [documents, setDocuments] = useState<PlainDocument[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const owner = session.user?.email ?? "";
  const loadedFor = useRef("");
  const current = useRef<PlainDocument[]>([]);
  current.current = documents;

  const reload = useCallback(() => {
    setError("");
    allDocuments()
      .then((items) => withVault((vault) => decryptOwned(vault, items)))
      .then((plain) => {
        setDocuments((current) => [...current.filter((doc) => doc.status), ...plain]);
        setLoaded(true);
      }, (cause) => setError(errorMessage(cause)));
  }, [withVault]);

  // Forget everything on logout / account switch.
  useEffect(() => {
    if (loadedFor.current && loadedFor.current !== owner) {
      setDocuments([]);
      setLoaded(false);
      loadedFor.current = "";
    }
  }, [owner]);

  /** Pages that need the library call this; the vault is only requested then. */
  const ensureLoaded = useCallback(() => {
    if (!owner || loadedFor.current === owner) return;
    loadedFor.current = owner;
    reload();
  }, [owner, reload]);

  // Optimistic: the encrypted upload shows at once and is reconciled when the server answers.
  const submitUpload = useCallback((draft: Omit<PlainDocument, "status">, form: FormData) => {
    setDocuments((list) => [{ ...draft, status: "sending" }, ...list]);
    api.uploadDocument(form).then(
      () => setDocuments((list) => list.map((doc) => (doc.id === draft.id ? { ...draft } : doc))),
      (cause) => setDocuments((list) => list.map((doc) => (doc.id === draft.id
        ? { ...doc, status: "failed", error: errorMessage(cause, "Não foi possível salvar o documento.") } : doc))),
    );
  }, []);

  const dismiss = useCallback((id: string) => setDocuments((list) => list.filter((doc) => doc.id !== id)), []);

  const remove = useCallback(async (ids: string[]) => {
    const doomed = new Set(ids);
    const removed = current.current.filter((doc) => doomed.has(doc.id));
    setDocuments((list) => list.filter((doc) => !doomed.has(doc.id)));
    const results = await Promise.allSettled(ids.map((id) => api.deleteDocument(id)));
    const failed = new Set(ids.filter((_, index) => results[index].status === "rejected"));
    if (failed.size) {
      setDocuments((list) => [...removed.filter((doc) => failed.has(doc.id)), ...list]);
      throw new Error(failed.size === 1 ? "Não foi possível excluir um documento." : `Não foi possível excluir ${failed.size} documentos.`);
    }
  }, []);

  return (
    <DocumentsContext.Provider value={{ documents, loaded, error, reload, ensureLoaded, submitUpload, dismiss, remove }}>
      {children}
    </DocumentsContext.Provider>
  );
}

export function useDocuments(): DocumentsContextValue {
  const value = useContext(DocumentsContext);
  if (!value) throw new Error("useDocuments outside DocumentsProvider");
  const { ensureLoaded } = value;
  useEffect(ensureLoaded, [ensureLoaded]);
  return value;
}

/** Only fully stored documents can be shared. */
export const shareable = (documents: PlainDocument[]) => documents.filter((doc) => !doc.status);
