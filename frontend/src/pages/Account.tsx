import { AtSign, Bell, BellOff, Copy, LogOut, Printer, Scale, Smartphone } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { Alert } from "../components/Alert";
import { api, type Profile } from "../lib/api";
import { errorMessage } from "../lib/format";
import { disablePush, enablePush, pushStatus, type PushStatus } from "../lib/push";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";
import { useInstallPrompt } from "../lib/pwa";
import { CONTACT_EMAIL } from "../lib/brand";

const PUSH_TEXT: Record<PushStatus, string> = {
  unsupported: "Este navegador não recebe notificações. No iPhone, adicione o Pode Abrir à tela de início primeiro.",
  unconfigured: "Notificações ainda não foram configuradas neste servidor.",
  denied: "As notificações foram bloqueadas nas configurações do navegador.",
  on: "Você recebe um aviso quando alguém pede para ler ou abre um link seu.",
  off: "Receba um aviso quando alguém pedir para ler ou abrir um link seu.",
};

export function Account() {
  const { session, setSession } = useSession();
  const { forgetVault } = useVault();
  const navigate = useNavigate();
  const install = useInstallPrompt();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [handle, setHandle] = useState("");
  const [active, setActive] = useState(false);
  const [push, setPush] = useState<PushStatus>("off");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.profile().then(async (current) => {
      setProfile(current);
      setHandle(current.handle ?? "");
      setActive(current.handle_active);
      setPush(await pushStatus(current.push_public_key));
    }, (cause) => setError(errorMessage(cause)));
  }, []);

  async function saveHandle(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSaved(false);
    try {
      setProfile(await api.updateProfile(handle.trim().replace(/^@/, "").toLowerCase(), active));
      setSaved(true);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  async function togglePush() {
    setError("");
    try {
      setPush(push === "on" ? await disablePush() : await enablePush(profile!.push_public_key));
    } catch (cause) {
      setError(errorMessage(cause, "Não foi possível ativar as notificações."));
    }
  }

  if (!profile) return <Alert message={error} />;
  const live = profile.handle && profile.handle_active;

  return (
    <div className="narrow">
      <div className="page-heading"><div><h1>Conta</h1><p className="muted">{session.user?.email}</p></div></div>
      <Alert message={error} />

      <section className="surface form-card">
        <h2><AtSign size={18} aria-hidden="true" /> Endereço pessoal</h2>
        <p className="muted">
          Um endereço fácil de dizer, como <strong>podeabrir.com/@ana</strong>. Quem abre pede para ler; você aprova no
          celular conferindo um código. A página não mostra seu nome nem confirma que o endereço existe.
        </p>
        {!live && (
          <p className="notice" role="note">
            {profile.handle
              ? <>Endereço desativado: pedidos feitos em <strong>@{profile.handle}</strong> não chegam até você.</>
              : <>Nenhum endereço ativo: pedidos feitos em qualquer <strong>podeabrir.com/@nome</strong> não chegam até você.</>}
            {" "}Por privacidade, quem pede vê a mesma tela de espera.
          </p>
        )}
        <form className="form-grid" onSubmit={saveHandle}>
          <div>
            <label htmlFor="handle">Seu endereço</label>
            <div className="prefixed">
              <span>podeabrir.com/@</span>
              <input id="handle" autoCapitalize="none" spellCheck={false} minLength={3} maxLength={30} required
                pattern="[A-Za-z0-9][A-Za-z0-9._\-]{1,28}[A-Za-z0-9]" placeholder="ana.consultas"
                value={handle} onChange={(event) => setHandle(event.target.value)} />
            </div>
            <small>Evite seu nome completo se não quiser ser encontrado por ele.</small>
          </div>
          <label className="choice">
            <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
            <span>Receber pedidos neste endereço</span>
          </label>
          <button className="button primary">{saved ? "Salvo" : "Salvar"}</button>
        </form>
        {live && (
          <div className="address-card">
            <img src={profile.address_qr} width={168} height={168} alt={`QR para ${profile.address}`} />
            <div>
              <p className="mono">{profile.address.replace(/^https?:\/\//, "")}</p>
              <p className="muted">Imprima e deixe no balcão, ou mostre no celular.</p>
              <div className="actions tight">
                <button type="button" className="button secondary" onClick={() => navigator.clipboard.writeText(profile.address)}>
                  <Copy size={16} aria-hidden="true" />Copiar
                </button>
                <button type="button" className="button secondary" onClick={() => window.print()}>
                  <Printer size={16} aria-hidden="true" />Imprimir cartão
                </button>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className="surface form-card">
        <h2>{push === "on" ? <Bell size={18} aria-hidden="true" /> : <BellOff size={18} aria-hidden="true" />} Notificações</h2>
        <p className="muted">{PUSH_TEXT[push]}</p>
        {(push === "on" || push === "off") && (
          <div className="actions">
            <button className={push === "on" ? "button secondary" : "button primary"} onClick={togglePush}>
              {push === "on" ? "Desativar neste dispositivo" : "Ativar neste dispositivo"}
            </button>
          </div>
        )}
      </section>

      <section className="surface form-card">
        <h2><Smartphone size={18} aria-hidden="true" /> App no celular</h2>
        <p className="muted">
          {install.status === "installed"
            ? "Você está usando o app instalado."
            : "Instale o pode abrir na tela inicial para abrir como aplicativo. No iPhone, as notificações só funcionam com o app instalado."}
        </p>
        {install.status !== "installed" && <div className="actions"><Link className="button secondary" to="/instalar/">Como instalar</Link></div>}
      </section>

      <section className="surface form-card">
        <h2><Scale size={18} aria-hidden="true" /> Privacidade e seus dados (LGPD)</h2>
        <p className="muted">
          Você aceitou os <Link to="/termos/">Termos de Uso</Link> e a <Link to="/privacidade/">Política de Privacidade</Link>{" "}
          (versão {session.legal_version}). Para acessar, corrigir, levar ou excluir seus dados, ou revogar o consentimento,
          escreva para <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Respondemos em até 15 dias.
        </p>
      </section>

      <div className="actions account-footer">
        {session.user?.is_staff && <Link to="/administracao/">Administração</Link>}
        <button type="button" className="button ghost" onClick={() => {
          forgetVault();
          setSession({ ...session, user: null });
          navigate("/");
          api.logout().catch(() => api.session()).then(setSession, () => {});
        }}><LogOut size={16} aria-hidden="true" />Sair</button>
      </div>
    </div>
  );
}
