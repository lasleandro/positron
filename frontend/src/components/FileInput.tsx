import { FileUp } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";

interface Props {
  id: string;
  accept: string;
  required?: boolean;
  onChange: (file: File | null) => void;
  /** File dropped elsewhere (e.g. on the library) that should arrive already attached. */
  initialFile?: File | null;
}

/** Drag-and-drop zone ("arraste e solte") with a Portuguese file button. Dropped files go into
 * the real <input type=file>, so required/validation and keyboard use keep working. */
export function FileInput({ id, accept, required, onChange, initialFile }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);

  function choose(file: File | null) {
    setName(file?.name ?? "");
    onChange(file);
  }

  /** Put a file into the real input (keeps native required validation). */
  function attach(file: File) {
    if (!input.current) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.current.files = transfer.files;
    choose(file);
  }

  useEffect(() => {
    if (initialFile) attach(initialFile);
  }, [initialFile]); // eslint-disable-line react-hooks/exhaustive-deps

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) attach(file);
  }

  return (
    <label className={dragging ? "file-picker dropzone dragging" : "file-picker dropzone"} htmlFor={id}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
      onDrop={drop}>
      <input ref={input} id={id} type="file" accept={accept} required={required} className="file-native"
        onChange={(event) => choose(event.target.files?.[0] ?? null)} />
      <FileUp size={26} className="dropzone-icon" aria-hidden="true" />
      <span className="dropzone-text">
        {name
          ? <strong className="file-name">{name}</strong>
          : <><strong>Arraste e solte o PDF aqui</strong><span className="muted">ou</span></>}
      </span>
      <span className="button secondary">{name ? "Trocar arquivo" : "Escolher arquivo"}</span>
    </label>
  );
}
