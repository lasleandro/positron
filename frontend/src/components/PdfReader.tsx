import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";

import { errorMessage } from "../lib/format";
import { burnWatermark, type Watermark } from "../lib/watermark";

GlobalWorkerOptions.workerSrc = workerUrl;
const ASSETS = "/pdfjs/";
const MIN_ZOOM = 0.75;
const MAX_ZOOM = 2.5;

export interface ReaderDocument { id: string; title: string }

interface Props {
  doc: ReaderDocument | null;
  /** Fetch and decrypt the document locally; must be referentially stable. */
  open: (id: string, signal: AbortSignal) => Promise<Uint8Array<ArrayBuffer>>;
  /** Burned into the page pixels for grantees (who / when / reference / legal notice). */
  watermark?: Watermark;
}

export function PdfReader({ doc, open, watermark }: Props) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [status, setStatus] = useState("");
  const [resizeTick, setResizeTick] = useState(0);
  const viewport = useRef<HTMLDivElement>(null);
  const output = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onResize = () => setResizeTick((tick) => tick + 1);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    setPdf(null);
    output.current?.replaceChildren();
    if (!doc) {
      setStatus("");
      return;
    }
    const controller = new AbortController();
    let loading: ReturnType<typeof getDocument> | null = null;
    let cancelled = false;
    setStatus("Decifrando neste navegador…");
    (async () => {
      try {
        const data = await open(doc.id, controller.signal);
        if (cancelled) return;
        loading = getDocument({
          data,
          cMapUrl: ASSETS + "cmaps/",
          cMapPacked: true,
          iccUrl: ASSETS + "iccs/",
          standardFontDataUrl: ASSETS + "standard_fonts/",
          wasmUrl: ASSETS + "wasm/",
        });
        const loaded = await loading.promise;
        if (cancelled) return;
        setPage(1);
        setZoom(1);
        setPdf(loaded);
        setStatus("");
      } catch (error) {
        if (cancelled) return;
        setStatus(error instanceof Error && error.name === "OperationError"
          ? "Não foi possível abrir o documento com a chave desta sessão."
          : errorMessage(error, "Não foi possível abrir o PDF."));
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
      loading?.destroy().catch(() => {});
      output.current?.replaceChildren();
    };
  }, [doc, open]);

  useEffect(() => {
    if (!pdf || !viewport.current || !output.current) return;
    const frame = viewport.current;
    const target = output.current;
    let cancelled = false;
    let rendering: { cancel: () => void } | null = null;
    (async () => {
      try {
        const pdfPage = await pdf.getPage(page);
        if (cancelled) return;
        const original = pdfPage.getViewport({ scale: 1 });
        const availableWidth = Math.max(150, frame.clientWidth - 32);
        const view = pdfPage.getViewport({ scale: Math.min(1.35, availableWidth / original.width) * zoom });
        const ratio = Math.min(window.devicePixelRatio || 1, 2, 4096 / view.width, 4096 / view.height);
        const canvas = document.createElement("canvas");
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", `Página ${page} do documento`);
        canvas.width = Math.max(1, Math.floor(view.width * ratio));
        canvas.height = Math.max(1, Math.floor(view.height * ratio));
        canvas.style.width = Math.ceil(view.width) + "px";
        canvas.style.height = Math.ceil(view.height) + "px";
        const task = pdfPage.render({ canvas, viewport: view, transform: [ratio, 0, 0, ratio, 0, 0] });
        rendering = task;
        await task.promise;
        if (cancelled) return;
        if (watermark) burnWatermark(canvas, watermark, page);
        target.replaceChildren(canvas);
        frame.scrollTop = 0;
      } catch {
        if (!cancelled) setStatus("Não foi possível exibir esta página.");
      }
    })();
    return () => {
      cancelled = true;
      rendering?.cancel();
    };
  }, [pdf, page, zoom, resizeTick, watermark]);

  const pages = pdf?.numPages ?? 0;
  return (
    <section className="surface reader" aria-label="Leitor de PDF">
      <header className="reader-head">
        <h2>{doc?.title ?? "Documento"}</h2>
        <div className="reader-controls" aria-label="Controles do PDF">
          <button className="icon-button" type="button" aria-label="Página anterior"
            disabled={!pdf || page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={18} /></button>
          <span className="page-count">{pdf ? `${page} / ${pages}` : "—"}</span>
          <button className="icon-button" type="button" aria-label="Próxima página"
            disabled={!pdf || page >= pages} onClick={() => setPage(page + 1)}><ChevronRight size={18} /></button>
          <span className="divider" aria-hidden="true" />
          <button className="icon-button" type="button" aria-label="Reduzir zoom"
            disabled={!pdf || zoom <= MIN_ZOOM} onClick={() => setZoom(Math.max(MIN_ZOOM, zoom - 0.25))}><ZoomOut size={18} /></button>
          <button className="icon-button" type="button" aria-label="Aumentar zoom"
            disabled={!pdf || zoom >= MAX_ZOOM} onClick={() => setZoom(Math.min(MAX_ZOOM, zoom + 0.25))}><ZoomIn size={18} /></button>
        </div>
      </header>
      {status && <p className="reader-status" role="status">{status}</p>}
      <div className="canvas-viewport" ref={viewport} tabIndex={0} aria-label="Página do documento"
        onContextMenu={(event) => event.preventDefault()}>
        <div className="pdf-stage">
          <div className="pdf-page" ref={output} />
        </div>
      </div>
    </section>
  );
}
