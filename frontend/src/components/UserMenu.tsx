import { ChevronDown, LogOut, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router";

/** Top-right account menu: Conta, Administração (admins only) and Sair. */
export function UserMenu({ email, isAdmin, onLogout }: { email: string; isAdmin: boolean; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <div className="user-menu" ref={root}>
      <button type="button" className="user-menu-button" aria-haspopup="menu" aria-expanded={open}
        aria-label={`Menu da conta ${email}`} onClick={() => setOpen((value) => !value)}>
        <UserRound size={18} aria-hidden="true" />
        <span className="user-menu-email">{email}</span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      {open && (
        <div className="user-menu-panel" role="menu">
          <p className="user-menu-who">{email}{isAdmin && <small>Administrador</small>}</p>
          <NavLink role="menuitem" to="/conta/"><UserRound size={16} aria-hidden="true" />Conta</NavLink>
          {isAdmin && <NavLink role="menuitem" to="/administracao/"><ShieldCheck size={16} aria-hidden="true" />Administração</NavLink>}
          <button type="button" role="menuitem" onClick={onLogout}><LogOut size={16} aria-hidden="true" />Sair</button>
        </div>
      )}
    </div>
  );
}
