import {
  ArrowDown, ArrowUp, ArrowUpDown, CircleAlert, Download, Eye, FileLock2, Link2, MonitorSmartphone, Plus, Search, Trash2, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { Alert } from "../components/Alert";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { api } from "../lib/api";
import { decode, openPdf, unseal } from "../lib/crypto";
import { useDocuments, type PlainDocument } from "../lib/documents";
import { errorMessage, formatDate } from "../lib/format";
import { useVault } from "../lib/vault";

type SortKey = "title" | "document_date" | "issuer";
interface Sort { key: SortKey; dir: "asc" | "desc" }

const normalize = (value: string) => value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
const collator = new Intl.Collator("pt-BR", { sensitivity: "base", numeric: true });
const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "title", label: "Nome" }, { key: "document_date", label: "Data" }, { key: "issuer", label: "Emissor" },
];

function compare(a: PlainDocument, b: PlainDocument, { key, dir }: Sort): number {
  const order = key === "document_date" ? a.document_date.localeCompare(b.document_date) : collator.compare(a[key], b[key]);
  return dir === "asc" ? order : -order;
}

export function Library() {
  const { documents, loaded, error, dismiss, remove } = useDocuments();
  const { withVault } = useVault();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>({ key: "document_date", dir: "desc" });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null);
  const [actionError, setActionError] = useState("");
  const [dragging, setDragging] = useState(false);
  const selectAll = useRef<HTMLInputElement>(null);

  const uploads = documents.filter((doc) => doc.status);
  // Titles are decrypted in this browser, so search and sort happen here: the server cannot read them.
  const rows = useMemo(() => {
    const needle = normalize(query.trim());
    const stored = documents.filter((doc) => !doc.status);
    const matching = needle ? stored.filter((doc) => normalize(`${doc.title} ${doc.issuer}`).includes(needle)) : stored;
    return [...matching].sort((a, b) => compare(a, b, sort));
  }, [documents, query, sort]);

  // Selection only ever contains rows that still exist.
  useEffect(() => {
    setSelected((current) => {
      const alive = new Set(documents.map((doc) => doc.id));
      const next = new Set([...current].filter((id) => alive.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [documents]);

  const visibleSelected = rows.filter((doc) => selected.has(doc.id)).length;
  useEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = visibleSelected > 0 && visibleSelected < rows.length;
  }, [visibleSelected, rows.length]);

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(visibleSelected === rows.length ? new Set() : new Set(rows.map((doc) => doc.id)));
  }

  function sortBy(key: SortKey) {
    setSort((current) => current.key === key
      ? { key, dir: current.dir === "asc" ? "desc" : "asc" }
      : { key, dir: key === "document_date" ? "desc" : "asc" });
  }

  const share = (ids: string[], to: "/compartilhar/" | "/autorizar/") => navigate(to, { state: { documents: ids } });

  async function download(doc: PlainDocument) {
    setActionError("");
    try {
      const { ciphertext, wrappedKey } = await api.documentContent(doc.id);
      const rawKey = await withVault((vault) => unseal(vault, decode(wrappedKey), "owner", doc.id));
      const pdf = await openPdf(rawKey, ciphertext, doc.id);
      const url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${doc.title.replace(/[\\/:*?"<>|]+/g, " ").trim() || "documento"}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setActionError(errorMessage(cause, "Não foi possível baixar o documento."));
    }
  }

  function confirmDelete() {
    const ids = pendingDelete ?? [];
    setPendingDelete(null);
    setActionError("");
    remove(ids).catch((cause) => setActionError(errorMessage(cause)));
  }

  const doomedTitles = (pendingDelete ?? []).map((id) => documents.find((doc) => doc.id === id)?.title ?? "").filter(Boolean);
  const selection = [...selected];

  return (
    <>
      <div className="page-heading">
        <div><h1>Seus documentos</h1><p className="muted">Cifrados neste dispositivo. Nem o servidor consegue ler os nomes.</p></div>
        <Link className="button primary" to="/enviar/"><Plus size={18} aria-hidden="true" />Adicionar PDF</Link>
      </div>
      <Alert message={actionError} />
      <section className={dragging ? "surface library drop-target dragging" : "surface library drop-target"}
        onDragOver={(event) => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) navigate("/enviar/", { state: { file } });
        }}>
        {dragging && <div className="drop-overlay" aria-hidden="true"><FileLock2 size={28} />Solte para adicionar e cifrar</div>}
        {selection.length > 0 ? (
          <div className="bulk-bar" role="toolbar" aria-label="Ações para os documentos selecionados">
            <strong>{selection.length} selecionado{selection.length > 1 ? "s" : ""}</strong>
            <div className="actions tight">
              <button className="button primary" onClick={() => share(selection, "/compartilhar/")}><Link2 size={16} aria-hidden="true" />Compartilhar por link</button>
              <button className="button secondary" onClick={() => share(selection, "/autorizar/")}><MonitorSmartphone size={16} aria-hidden="true" />Leitura presencial</button>
              <button className="button danger" onClick={() => setPendingDelete(selection)}><Trash2 size={16} aria-hidden="true" />Excluir</button>
              <button className="icon-button" onClick={() => setSelected(new Set())} aria-label="Limpar seleção" title="Limpar seleção"><X size={16} /></button>
            </div>
          </div>
        ) : (
          <div className="search" role="search">
            <Search size={18} className="search-icon" aria-hidden="true" />
            <label className="sr-only" htmlFor="buscar">Buscar documento ou emissor</label>
            <input id="buscar" type="search" placeholder="Buscar documento ou emissor" maxLength={100}
              value={query} onChange={(event) => setQuery(event.target.value)} />
          </div>
        )}
        {error && <p className="alert pad" role="alert">{error}</p>}

        {uploads.length > 0 && (
          <ul className="exam-list uploads">
            {uploads.map((doc) => (
              <li key={doc.id} className={doc.status === "failed" ? "row failed" : "row pending"}>
                {doc.status === "failed" ? <CircleAlert size={18} aria-hidden="true" /> : <FileLock2 size={18} aria-hidden="true" />}
                <span className="row-title">{doc.title}</span>
                <span className="row-meta">{doc.status === "failed" ? doc.error : "Enviando cifrado…"}</span>
                {doc.status === "failed" && <button className="button ghost" onClick={() => dismiss(doc.id)}>Descartar</button>}
              </li>
            ))}
          </ul>
        )}

        {loaded && rows.length === 0 && uploads.length === 0 && (
          <p className="empty">{query ? "Nenhum documento corresponde à busca." : "Adicione seu primeiro documento em PDF."}</p>
        )}
        {rows.length > 0 && (
          <div className="table-scroll">
            <table className="doc-table">
              <thead>
                <tr>
                  <th scope="col" className="col-check">
                    <input ref={selectAll} type="checkbox" aria-label="Selecionar todos"
                      checked={rows.length > 0 && visibleSelected === rows.length} onChange={toggleAll} />
                  </th>
                  {COLUMNS.map(({ key, label }) => {
                    const active = sort.key === key;
                    const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
                    return (
                      <th key={key} scope="col" className={`col-${key}`}
                        aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
                        <button type="button" className={active ? "sort on" : "sort"} onClick={() => sortBy(key)}>
                          {label}<Icon size={14} aria-hidden="true" />
                        </button>
                      </th>
                    );
                  })}
                  <th scope="col" className="col-actions"><span className="sr-only">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((doc) => (
                  <tr key={doc.id} className={selected.has(doc.id) ? "selected" : undefined}>
                    <td className="col-check">
                      <input type="checkbox" checked={selected.has(doc.id)} onChange={() => toggle(doc.id)}
                        aria-label={`Selecionar ${doc.title}`} />
                    </td>
                    <th scope="row" className="col-title">
                      <Link to={`/documentos/${doc.id}/`}><FileLock2 size={16} aria-hidden="true" />{doc.title}</Link>
                    </th>
                    <td className="col-document_date">{formatDate(doc.document_date)}</td>
                    <td className="col-issuer">{doc.issuer || "—"}</td>
                    <td className="col-actions">
                      <div className="row-actions">
                        <Link className="icon-button" to={`/documentos/${doc.id}/`} aria-label={`Abrir ${doc.title}`} title="Abrir"><Eye size={16} /></Link>
                        <button className="icon-button" onClick={() => share([doc.id], "/compartilhar/")} aria-label={`Compartilhar ${doc.title}`} title="Compartilhar por link"><Link2 size={16} /></button>
                        <button className="icon-button" onClick={() => download(doc)} aria-label={`Baixar ${doc.title}`} title="Baixar"><Download size={16} /></button>
                        <button className="icon-button danger-icon" onClick={() => setPendingDelete([doc.id])} aria-label={`Excluir ${doc.title}`} title="Excluir"><Trash2 size={16} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="actions">
        <Link className="button secondary" to="/autorizar/">Autorizar leitura presencial</Link>
        <Link to="/compartilhamentos/">Ver compartilhamentos</Link>
      </div>

      <ConfirmDialog open={pendingDelete !== null} danger confirmLabel="Excluir definitivamente"
        title={doomedTitles.length > 1 ? `Excluir ${doomedTitles.length} documentos?` : "Excluir documento?"}
        onConfirm={confirmDelete} onCancel={() => setPendingDelete(null)}>
        <p>{doomedTitles.length > 1 ? doomedTitles.join(", ") : doomedTitles[0]}</p>
        <p>O arquivo cifrado é apagado do servidor e não pode ser recuperado. Compartilhamentos que ficarem sem documentos são encerrados.</p>
      </ConfirmDialog>
    </>
  );
}
