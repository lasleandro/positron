import { CircleAlert, MailCheck, Send } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "../lib/api";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";

interface Sent { email: string; error?: string }

export function Invitations() {
  const { session } = useSession();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<Sent[]>([]);

  function invite(event: FormEvent) {
    event.preventDefault();
    const target = email.trim().toLowerCase();
    // Optimistic: listed as sent at once; marked as failed if the server refuses.
    setSent((list) => [{ email: target }, ...list.filter((item) => item.email !== target)]);
    setEmail("");
    api.createInvitation(target).catch((cause) => {
      setSent((list) => list.map((item) => (item.email === target ? { ...item, error: errorMessage(cause) } : item)));
    });
  }

  return (
    <section className="surface form-card narrow">
      <h1>Convites</h1>
      <p className="muted">
        O convite é enviado ao email da pessoa, vale uma vez e expira em {session.limits.invitation_hours} horas.
        A conta fica vinculada a esse endereço.
      </p>
      <form className="form-grid" onSubmit={invite}>
        <div>
          <label htmlFor="invite-email">Email da pessoa convidada</label>
          <div className="copy-row">
            <input id="invite-email" type="email" maxLength={150} required autoComplete="off"
              value={email} onChange={(event) => setEmail(event.target.value)} />
            <button className="button primary"><Send size={16} aria-hidden="true" />Enviar</button>
          </div>
        </div>
      </form>
      {sent.length > 0 && (
        <ul className="sent-list">
          {sent.map((item) => (
            <li key={item.email} className={item.error ? "failed" : ""}>
              {item.error ? <CircleAlert size={16} aria-hidden="true" /> : <MailCheck size={16} aria-hidden="true" />}
              <span>{item.email}</span>
              <small>{item.error ?? "Convite enviado"}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
