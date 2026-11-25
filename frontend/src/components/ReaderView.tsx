import { useEffect, useState } from "react";

import { Countdown } from "./Countdown";
import { PdfReader, type ReaderDocument } from "./PdfReader";

export interface ReaderEntry { id: string; title: string; subtitle: string }

interface Props {
  heading: string;
  entries: ReaderEntry[];
  until: number;
  watermark: string;
  open: (id: string, signal: AbortSignal) => Promise<Uint8Array<ArrayBuffer>>;
  onExpire?: () => void;
}

/** Read-only viewer for grantees: countdown, watermark, no download, closes when access ends. */
export function ReaderView({ heading, entries, until, watermark, open, onExpire }: Props) {
  const [selected, setSelected] = useState<ReaderDocument | null>(null);
  useEffect(() => {
    setSelected(entries[0] ? { id: entries[0].id, title: entries[0].title } : null);
  }, [entries]);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{heading}</h1>
          <p className="muted">Somente leitura. O download está desativado.</p>
        </div>
        <Countdown until={until} onEnd={onExpire} />
      </div>
      <div className="reading-grid">
        <aside className="surface exam-panel" aria-label="Documentos compartilhados">
          {entries.map((entry) => (
            <button key={entry.id} type="button" className="exam-button" aria-pressed={selected?.id === entry.id}
              onClick={() => setSelected({ id: entry.id, title: entry.title })}>
              <strong>{entry.title}</strong>
              <small>{entry.subtitle}</small>
            </button>
          ))}
        </aside>
        <PdfReader doc={selected} open={open} watermark={watermark} />
      </div>
    </>
  );
}
