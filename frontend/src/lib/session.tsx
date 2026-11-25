import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api, type Session } from "./api";

interface SessionContextValue {
  session: Session;
  setSession: (session: Session) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.session().then(setSession, () => setFailed(true));
  }, []);

  if (failed) return <p className="boot-message">Não foi possível conectar ao servidor. Atualize a página.</p>;
  if (!session) return null;
  return <SessionContext.Provider value={{ session, setSession }}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession outside SessionProvider");
  return value;
}
