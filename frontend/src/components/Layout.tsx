import { BellRing, FileLock2, Mail, MonitorSmartphone, ShieldCheck, UserRound } from "lucide-react";
import { NavLink, Link, Outlet, useLocation, useNavigate } from "react-router";

import symbol from "../../assets/svg/pode-abrir-simbolo-grafite.svg";
import wordmark from "../../assets/svg/pode-abrir-assinatura-grafite.svg";
import { api } from "../lib/api";
import { CONTACT_EMAIL } from "../lib/brand";
import { usePendingRequests } from "../lib/pending";
import { ConsentGate } from "./ConsentGate";
import { CookieNotice } from "./CookieNotice";
import { InstallBanner } from "./InstallBanner";
import { UserMenu } from "./UserMenu";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";

function OwnerNav({ pending }: { pending: number }) {
  const { session, setSession } = useSession();
  const { forgetVault } = useVault();
  const navigate = useNavigate();

  function logout() {
    // Optimistic: leave immediately, then reconcile with whatever the server says.
    forgetVault();
    setSession({ ...session, user: null });
    navigate("/");
    api.logout().catch(() => api.session()).then(setSession, () => {});
  }

  return (
    <div className="owner-header">
      <nav aria-label="Área pessoal">
        <NavLink to="/documentos/">Documentos</NavLink>
        <NavLink to="/compartilhamentos/">
          Compartilhamentos{pending > 0 && <span className="nav-badge" aria-label={`${pending} pedido(s) de leitura`}>{pending}</span>}
        </NavLink>
      </nav>
      <UserMenu email={session.user?.email ?? ""} isAdmin={Boolean(session.user?.is_staff)} onLogout={logout} />
    </div>
  );
}

function PublicNav() {
  return (
    <nav aria-label="Navegação">
      <NavLink to="/entrar/">Entrar</NavLink>
      <NavLink to="/ler/" className="nav-cta"><FileLock2 size={16} aria-hidden="true" />Ler documentos</NavLink>
    </nav>
  );
}

/** Shown on every owner page while someone waits for approval at podeabrir.com/@nome. */
function PendingBanner({ items }: { items: { id: string }[] }) {
  const { pathname } = useLocation();
  if (!items.length || pathname.startsWith("/autorizar/pedido") || pathname.startsWith("/compartilhamentos")) return null;
  return (
    <div className="pending-banner" role="status">
      <BellRing size={18} aria-hidden="true" />
      <span>{items.length > 1 ? `${items.length} pessoas pediram` : "Alguém pediu"} para ler seus documentos agora.</span>
      <Link className="button primary" to={items.length > 1 ? "/compartilhamentos/" : `/autorizar/pedido/${items[0].id}`}>
        Conferir e aprovar
      </Link>
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-content">
        <div className="footer-brand">
          <img src={symbol} alt="" width={28} height={28} />
          <span>Compartilhamento efêmero e cifrado de documentos.</span>
        </div>
        <a className="footer-contact" href={`mailto:${CONTACT_EMAIL}`}><Mail size={16} aria-hidden="true" />{CONTACT_EMAIL}</a>
        <nav className="footer-legal" aria-label="Informações legais">
          <Link to="/privacidade/">Privacidade</Link>
          <Link to="/privacidade/#cookies">Cookies</Link>
          <Link to="/termos/">Termos</Link>
        </nav>
        <small>© {new Date().getFullYear()} pode abrir</small>
      </div>
    </footer>
  );
}

/** Phone navigation for owners: thumb-reachable tabs (the top menu is hidden on small screens). */
function TabBar({ pending }: { pending: number }) {
  return (
    <nav className="tab-bar" aria-label="Navegação do app">
      <NavLink to="/documentos/"><FileLock2 size={22} aria-hidden="true" /><span>Documentos</span></NavLink>
      <NavLink to="/compartilhamentos/">
        <ShieldCheck size={22} aria-hidden="true" /><span>Compartilhar</span>
        {pending > 0 && <em className="tab-badge" aria-label={`${pending} pedido(s) de leitura`}>{pending}</em>}
      </NavLink>
      <NavLink to="/ler/"><MonitorSmartphone size={22} aria-hidden="true" /><span>Ler</span></NavLink>
      <NavLink to="/conta/"><UserRound size={22} aria-hidden="true" /><span>Conta</span></NavLink>
    </nav>
  );
}

const LEGAL_PATHS = ["/privacidade", "/termos"];

export function Layout() {
  const { session, setSession } = useSession();
  const { pathname } = useLocation();
  // Owners must accept the current Terms + Privacy version first; the legal pages stay readable.
  const gated = Boolean(session.user && !session.user.consent_ok) && !LEGAL_PATHS.some((path) => pathname.startsWith(path));
  const logout = () => {
    setSession({ ...session, user: null });
    api.logout().catch(() => api.session()).then(setSession, () => {});
  };
  const pending = usePendingRequests(Boolean(session.user));
  return (
    <div className={session.user ? "app-shell owner" : "app-shell"}>
      <a className="skip" href="#conteudo">Pular para o conteúdo</a>
      <header className="site-header">
        <div className="wrap header-content">
          <Link className="brand" to="/" aria-label="pode abrir, página inicial"><img src={wordmark} alt="pode abrir" width={148} height={32} /></Link>
          {session.user ? <OwnerNav pending={pending.length} /> : <PublicNav />}
        </div>
      </header>
      <main className="wrap" id="conteudo">
        {session.user && !gated && <PendingBanner items={pending} />}
        {gated ? <ConsentGate onLogout={logout} /> : <Outlet />}
      </main>
      <SiteFooter />
      <CookieNotice />
      {session.user && !gated && <InstallBanner />}
      {session.user && <TabBar pending={pending.length} />}
    </div>
  );
}
