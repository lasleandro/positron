import { ArrowLeft, Lock } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { Alert } from "../components/Alert";
import { DateInput } from "../components/DateInput";
import { FileInput } from "../components/FileInput";
import { sealPdf, sealText } from "../lib/crypto";
import { useDocuments } from "../lib/documents";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";

export function Upload() {
  const { session } = useSession();
  const { withVault } = useVault();
  const { submitUpload } = useDocuments();
  const navigate = useNavigate();
  const route = useLocation();
  // A PDF dropped on the library arrives here already attached, with its name as a suggestion.
  const [dropped] = useState<File | null>(() => (route.state as { file?: File } | null)?.file ?? null);
  const [title, setTitle] = useState(() => dropped?.name.replace(/\.pdf$/i, "") ?? "");
  const [documentDate, setDocumentDate] = useState("");
  const [issuer, setIssuer] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const maxMb = Math.round(session.limits.pdf_max_bytes / 1024 / 1024);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!file || file.size > session.limits.pdf_max_bytes) {
      setError(`Selecione um PDF de até ${maxMb} MB.`);
      return;
    }
    setBusy(true);
    try {
      if (await file.slice(0, 5).text() !== "%PDF-") throw new Error("Selecione um PDF válido.");
      const id = crypto.randomUUID();
      const pdf = await file.arrayBuffer();
      const { ciphertext, wrappedKey, rawKey } = await withVault((vault) => sealPdf(vault, pdf, id));
      const cleanTitle = title.trim();
      const cleanIssuer = issuer.trim();
      const form = new FormData();
      form.set("id", id);
      form.set("sealed_title", await sealText(rawKey, cleanTitle, "meta-title", id));
      form.set("sealed_issuer", cleanIssuer ? await sealText(rawKey, cleanIssuer, "meta-issuer", id) : "");
      form.set("document_date", documentDate);
      form.set("wrapped_key", wrappedKey);
      form.set("ciphertext", new Blob([ciphertext]), "documento.enc");
      submitUpload({ id, title: cleanTitle, issuer: cleanIssuer, document_date: documentDate, wrapped_key: wrappedKey }, form);
      navigate("/documentos/");
    } catch (cause) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  }

  return (
    <div className="narrow">
      <Link className="back" to="/documentos/"><ArrowLeft size={16} aria-hidden="true" />Voltar para documentos</Link>
      <section className="surface form-card">
        <h1>Adicionar documento</h1>
        <p className="muted">Exames, laudos, contratos, extratos, certidões. PDF de até {maxMb} MB.</p>
        <form className="form-grid" onSubmit={save}>
          <div>
            <label htmlFor="title">Nome do documento</label>
            <input id="title" maxLength={160} required placeholder="Ex.: Hemograma completo"
              value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="field-row">
            <div>
              <label htmlFor="document-date">Data</label>
              <DateInput id="document-date" required value={documentDate} onChange={setDocumentDate} />
            </div>
            <div>
              <label htmlFor="issuer">Emissor</label>
              <input id="issuer" maxLength={100} placeholder="Laboratório, empresa, cartório…"
                value={issuer} onChange={(event) => setIssuer(event.target.value)} />
            </div>
          </div>
          <div>
            <label htmlFor="local-pdf">Arquivo PDF</label>
            <FileInput id="local-pdf" accept="application/pdf,.pdf" required onChange={setFile} initialFile={dropped} />
          </div>
          <p className="note"><Lock size={14} aria-hidden="true" />Arquivo, nome e emissor são cifrados neste dispositivo antes do envio. Só a data fica legível, para ordenar.</p>
          <Alert message={error} />
          <button className="button primary" disabled={busy}>Salvar documento</button>
        </form>
      </section>
    </div>
  );
}
