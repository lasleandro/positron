import { CalendarDays } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface Props {
  id: string;
  /** ISO date "yyyy-mm-dd", or "" while empty/incomplete. */
  value: string;
  onChange: (iso: string) => void;
  required?: boolean;
}

const INVALID = "Informe uma data válida no formato dd/mm/aaaa.";

/** "01102026" -> "01/10/2026" as the user types (digits only). */
function mask(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join("/");
}

/** "01/10/2026" -> "2026-10-01" when it is a real calendar date, else "". */
function toIso(text: string): string {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
  if (!match) return "";
  const [, day, month, year] = match.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const real = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return real && year >= 1900 ? `${match[3]}-${match[2]}-${match[1]}` : "";
}

const fromIso = (iso: string) => (iso ? iso.split("-").reverse().join("/") : "");

/**
 * Date field that always reads dd/mm/aaaa (the app language), whatever the browser language.
 * The calendar button opens the browser's native picker through a hidden date input.
 */
export function DateInput({ id, value, onChange, required }: Props) {
  const [text, setText] = useState(() => fromIso(value));
  const field = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (value !== toIso(text)) setText(fromIso(value));
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const complete = text.length === 10;
    field.current?.setCustomValidity(text && (!complete || !toIso(text)) ? INVALID : "");
  }, [text]);

  function type(raw: string) {
    const next = mask(raw);
    setText(next);
    onChange(toIso(next));
  }

  function openCalendar() {
    const input = picker.current;
    if (!input) return;
    input.value = value;
    try {
      input.showPicker();
    } catch {
      field.current?.focus();
    }
  }

  return (
    <div className="date-field">
      <input ref={field} id={id} inputMode="numeric" autoComplete="off" placeholder="dd/mm/aaaa" maxLength={10}
        required={required} value={text} onChange={(event) => type(event.target.value)} />
      <button type="button" className="date-toggle" onClick={openCalendar} aria-label="Abrir calendário" title="Abrir calendário">
        <CalendarDays size={18} aria-hidden="true" />
      </button>
      <input ref={picker} type="date" className="date-picker-proxy" tabIndex={-1} aria-hidden="true"
        onChange={(event) => { setText(fromIso(event.target.value)); onChange(event.target.value); }} />
    </div>
  );
}
