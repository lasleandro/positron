import { ApiError } from "./api";

/** "2026-10-01" -> "01/10/2026" without timezone drift. */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

/** ISO timestamp -> "14:35" in the browser's local time. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function documentLine(document: { document_date: string; issuer: string }): string {
  return formatDate(document.document_date) + (document.issuer ? " · " + document.issuer : "");
}

const FIELD_LABELS: Record<string, string> = {
  token: "Link", email: "Email", password: "Senha", otp: "Código",
  sealed_title: "Nome", sealed_issuer: "Emissor", document_date: "Data", ciphertext: "Arquivo", handle: "Endereço",
};

export function errorMessage(error: unknown, fallback = "Não foi possível concluir a operação."): string {
  if (error instanceof ApiError && Object.keys(error.fields).length) {
    return Object.entries(error.fields).map(([field, message]) => `${FIELD_LABELS[field] ?? field}: ${message}`).join(" ");
  }
  return error instanceof Error && error.message ? error.message : fallback;
}


/** 45 -> "45 min", 120 -> "2 h", 10080 -> "7 dias". */
export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 24 * 60) return `${minutes / 60} h`;
  const days = minutes / (24 * 60);
  return days === 1 ? "24 h" : `${days} dias`;
}

/** Remaining time, compact: "04:59", "2 h 10 min", "3 dias". */
/** Ticking remaining time: 04:59, 23:04:59, 6 d 23:04:59. */
export function formatRemaining(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const two = (value: number) => String(value).padStart(2, "0");
  const clock = `${two(Math.floor((total % 3600) / 60))}:${two(total % 60)}`;
  if (total < 3600) return clock;
  const hours = Math.floor(total / 3600);
  if (hours < 24) return `${hours}:${clock}`;
  return `${Math.floor(hours / 24)} d ${two(hours % 24)}:${clock}`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
