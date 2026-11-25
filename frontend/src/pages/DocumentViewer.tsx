import { ArrowLeft } from "lucide-react";
import { useCallback, useMemo } from "react";
import { Link, useParams } from "react-router";

import { PdfReader } from "../components/PdfReader";
import { api } from "../lib/api";
import { decode, openPdf, unseal } from "../lib/crypto";
import { useDocuments } from "../lib/documents";
import { documentLine } from "../lib/format";
import { useVault } from "../lib/vault";

export function DocumentViewer() {
  const { documentId = "" } = useParams();
  const { withVault } = useVault();
  const { documents, loaded } = useDocuments();
  const document = documents.find((doc) => doc.id === documentId);

  const open = useCallback(async (id: string, signal: AbortSignal) => {
    const { ciphertext, wrappedKey } = await api.documentContent(id, signal);
    const rawKey = await withVault((vault) => unseal(vault, decode(wrappedKey), "owner", id));
    return openPdf(rawKey, ciphertext, id);
  }, [withVault]);

  const doc = useMemo(() => (document ? { id: document.id, title: document.title } : null), [document]);

  return (
    <>
      <Link className="back" to="/documentos/"><ArrowLeft size={16} aria-hidden="true" />Voltar para documentos</Link>
      {loaded && !document && <p className="alert" role="alert">Documento não encontrado.</p>}
      {document && (
        <div className="page-heading">
          <div><h1>{document.title}</h1><p className="muted">{documentLine(document)}</p></div>
        </div>
      )}
      {doc && <PdfReader doc={doc} open={open} />}
    </>
  );
}
