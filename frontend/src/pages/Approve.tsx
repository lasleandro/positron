import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { Alert } from "../components/Alert";
import { DocumentPicker } from "../components/DocumentPicker";
import { DurationSelect } from "../components/DurationSelect";
import { api, ApiError, type Grant } from "../lib/api";
import {
  comparisonCode, consultationKey, decode, encode, exportPublic, newKeyPair, PAIRING_CODE, publicFingerprint, seal,
  STORAGE, unseal,
} from "../lib/crypto";
import { shareable, useDocuments } from "../lib/documents";
import { errorMessage } from "../lib/format";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";

/** Code scanned from the reader QR (captured in main.tsx before any redirect to login). */
function takePairingCode(): string {
  const saved = sessionStorage.getItem(STORAGE.pairing) ?? "";
  sessionStorage.removeItem(STORAGE.pairing);
  return PAIRING_CODE.test(saved) ? saved : "";
}

interface Target { recipientKey: string; salt: string }

/** Approve a reader: in person (QR code) or a podeabrir.com/@nome request (grantId in the URL). */
export function Approve() {
  const { grantId } = useParams();
  const { session } = useSession();
  const { withVault } = useVault();
  const { documents } = useDocuments();
  const navigate = useNavigate();
  const [code, setCode] = useState(takePairingCode);
  const [request, setRequest] = useState<Grant | null>(null);
  const [comparison, setComparison] = useState("");
  const route = useLocation();
  // Rows selected in the library arrive preselected (multi-select there, no picking twice).
  const [chosen, setChosen] = useState<Set<string>>(
    () => new Set((route.state as { documents?: string[] } | null)?.documents ?? []),
  );
  const [minutes, setMinutes] = useState(session.limits.access_minutes);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const available = shareable(documents);

  useEffect(() => {
    if (!grantId) return;
    api.grants().then(async (grants) => {
      const found = grants.find((grant) => grant.id === grantId && grant.state === "pending");
      if (!found) return setError("Este pedido expirou ou já foi respondido.");
      setRequest(found);
      setComparison(await comparisonCode(found.recipient_key!, found.nonce!));
    }, (cause) => setError(errorMessage(cause)));
  }, [grantId]);

  /** In person: the QR carries a fingerprint of the reader key; refuse on any mismatch. */
  async function inPersonTarget(): Promise<Target> {
    const full = code.trim();
    if (!PAIRING_CODE.test(full)) throw new Error("Informe o código completo exibido na tela de leitura.");
    const [rawShort, confirmation] = full.split(".");
    const shortCode = rawShort.toUpperCase();
    const { recipient_key: recipientKey } = await api.pairingKey(shortCode).catch((cause) => {
      throw cause instanceof ApiError && cause.status === 404
        ? new Error("A solicitação expirou ou já foi usada. Gere outro código.") : cause;
    });
    if (await publicFingerprint(recipientKey) !== confirmation.toLowerCase()) {
      throw new Error("O código não corresponde à tela de leitura. Confira e tente de novo.");
    }
    return { recipientKey, salt: shortCode };
  }

  async function grant(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!chosen.size) return setError("Selecione pelo menos um documento.");
    setBusy(true);
    try {
      const target = request ? { recipientKey: request.recipient_key!, salt: request.nonce! } : await inPersonTarget();
      const { publicKey, privateKey } = await newKeyPair();
      const shared = await consultationKey(privateKey, target.recipientKey, target.salt);
      const selected = available.filter((doc) => chosen.has(doc.id));
      const shareKeys = await withVault((vault) => Promise.all(selected.map(async (doc) => {
        const dataKey = await unseal(vault, decode(doc.wrapped_key), "owner", doc.id);
        return [doc.id, encode(await seal(shared, dataKey, "recipient", doc.id))] as const;
      })));
      const body = {
        documents: selected.map((doc) => doc.id), share_keys: Object.fromEntries(shareKeys),
        sender_key: await exportPublic(publicKey), minutes,
      };
      if (request) await api.approveRequest(request.id, body);
      else await api.approveInPerson({ ...body, code: target.salt + "." + code.trim().split(".")[1].toLowerCase() });
      navigate("/compartilhamentos/");
    } catch (cause) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  }

  if (grantId && !request) {
    return (
      <section className="surface form-card narrow">
        <h1>Pedido de leitura</h1>
        <Alert message={error} />
        <p className="route-link"><Link to="/compartilhamentos/">Voltar para compartilhamentos</Link></p>
      </section>
    );
  }

  return (
    <section className="surface form-card narrow">
      <h1>{request ? "Pedido de leitura" : "Autorizar leitura presencial"}</h1>
      {request?.duplicate ? (
        <div className="warning" role="alert">
          <p><ShieldAlert size={18} aria-hidden="true" /><strong>Há outro pedido com o mesmo código.</strong></p>
          <p>Por segurança, recuse os dois e peça para a pessoa gerar um novo pedido.</p>
        </div>
      ) : request ? (
        <div className="verify">
          <ShieldCheck size={20} aria-hidden="true" />
          <div>
            <p>Confira se a tela de quem pediu mostra exatamente este código:</p>
            <p className="comparison-code">{comparison.slice(0, 3)} {comparison.slice(3)}</p>
            <p className="muted">Se for diferente, não aprove: outra pessoa pode estar tentando ler seus documentos.</p>
          </div>
        </div>
      ) : (
        <p className="muted">Confira o código da tela de leitura e escolha o que liberar.</p>
      )}
      {available.length === 0 && <p><Link to="/enviar/">Adicione um documento</Link> para compartilhar.</p>}
      {available.length > 0 && !request?.duplicate && (
        <form className="form-grid" onSubmit={grant}>
          {!request && (
            <div>
              <label htmlFor="pair-code">Código da tela de leitura</label>
              <input id="pair-code" className="mono" required maxLength={25} minLength={25} autoCapitalize="characters"
                spellCheck={false} autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} />
            </div>
          )}
          <DocumentPicker documents={available} chosen={chosen} onChange={setChosen} legend="Documentos que podem ser abertos" />
          <DurationSelect id="duration" label="Por quanto tempo" options={session.limits.in_person_minutes}
            value={minutes} onChange={setMinutes} />
          <Alert message={error} />
          <button className="button primary" disabled={busy}>
            <ShieldCheck size={18} aria-hidden="true" />Liberar documentos selecionados
          </button>
        </form>
      )}
    </section>
  );
}
