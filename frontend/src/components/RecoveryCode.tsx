import { Copy, Download, KeyRound } from "lucide-react";
import { useState } from "react";

interface Props {
  code: string;
  email: string;
  saved: boolean;
  onSavedChange: (saved: boolean) => void;
}

/** Shown exactly once. Without this code (and the password), reports cannot be recovered. */
export function RecoveryCode({ code, email, saved, onSavedChange }: Props) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
  }

  function download() {
    const body = `Pode Abrir - código de recuperação\nConta: ${email}\n\n${code}\n\n`
      + "Guarde este arquivo fora do celular e do computador que você usa no app.\n";
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "pode-abrir-codigo-de-recuperacao.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="recovery" aria-labelledby="recovery-title">
      <h2 id="recovery-title"><KeyRound size={18} aria-hidden="true" />Código de recuperação</h2>
      <p className="muted">
        Se esquecer a senha, este código é a única forma de manter seus documentos. Ele não fica salvo no servidor
        e não será exibido de novo.
      </p>
      <code className="recovery-code">{code}</code>
      <div className="actions">
        <button type="button" className="button secondary" onClick={copy}>
          <Copy size={16} aria-hidden="true" />{copied ? "Copiado" : "Copiar"}
        </button>
        <button type="button" className="button secondary" onClick={download}>
          <Download size={16} aria-hidden="true" />Baixar .txt
        </button>
      </div>
      <label className="choice">
        <input type="checkbox" checked={saved} onChange={(event) => onSavedChange(event.target.checked)} required />
        <span>Guardei o código de recuperação em um lugar seguro.</span>
      </label>
    </section>
  );
}
