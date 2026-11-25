import { BellRing, FileLock2, LogOut } from "lucide-react";
import { NavLink, Link, Outlet, useLocation, useNavigate } from "react-router";

import { api } from "../lib/api";
import { usePendingRequests } from "../lib/pending";
import { useSession } from "../lib/session";
import { useVault } from "../lib/vault";

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="10" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="16" cy="16" r="3.4" className="brand-dot" />
    </svg>
  );
}

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
    <nav aria-label="Área pessoal">
      <NavLink to="/documentos/">Documentos</NavLink>
      <NavLink to="/compartilhamentos/">
        Compartilhamentos{pending > 0 && <span className="nav-badge" aria-label={`${pending} pedido(s) de leitura`}>{pending}</span>}
      </NavLink>
      <NavLink to="/conta/">Conta</NavLink>
      {session.user?.is_staff && <NavLink to="/convites/">Convites</NavLink>}
      <button type="button" className="nav-button" onClick={logout}>
        <LogOut size={16} aria-hidden="true" /> Sair
      </button>
    </nav>
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

export function Layout() {
  const { session } = useSession();
  const pending = usePendingRequests(Boolean(session.user));
  return (
    <>
      <a className="skip" href="#conteudo">Pular para o conteúdo</a>
      <header className="site-header">
        <div className="wrap header-content">
          <Link className="brand" to="/"><BrandMark />Pode Abrir</Link>
          {session.user ? <OwnerNav pending={pending.length} /> : <PublicNav />}
        </div>
      </header>
      <main className="wrap" id="conteudo">
        {session.user && <PendingBanner items={pending} />}
        <Outlet />
      </main>
    </>
  );
}
