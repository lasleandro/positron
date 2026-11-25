import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "../lib/session";

/** Client-side guard only; every API call is still authorized on the server. */
export function RequireOwner({ children, staff = false }: { children: ReactNode; staff?: boolean }) {
  const { session } = useSession();
  const location = useLocation();
  if (!session.user) return <Navigate to={`/entrar/?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (staff && !session.user.is_staff) return <Navigate to="/documentos/" replace />;
  return children;
}
