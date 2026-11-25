import type { PlainDocument } from "../lib/documents";
import { documentLine } from "../lib/format";

interface Props {
  documents: PlainDocument[];
  chosen: Set<string>;
  onChange: (chosen: Set<string>) => void;
  legend?: string;
}

export function DocumentPicker({ documents, chosen, onChange, legend = "Documentos" }: Props) {
  function toggle(id: string) {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }
  return (
    <fieldset>
      <legend>{legend}</legend>
      {documents.map((document) => (
        <label key={document.id} className="choice">
          <input type="checkbox" checked={chosen.has(document.id)} onChange={() => toggle(document.id)} />
          <span><strong>{document.title}</strong><small>{documentLine(document)}</small></span>
        </label>
      ))}
    </fieldset>
  );
}
