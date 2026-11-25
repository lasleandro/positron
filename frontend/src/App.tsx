import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router";

import { Layout } from "./components/Layout";
import { RequireOwner } from "./components/RequireOwner";
import { DocumentsProvider } from "./lib/documents";
import { SessionProvider } from "./lib/session";
import { VaultProvider } from "./lib/vault";
import { Account } from "./pages/Account";
import { Admin } from "./pages/Admin";
import { Approve } from "./pages/Approve";
import { DocumentViewer } from "./pages/DocumentViewer";
import { Enroll } from "./pages/Enroll";
import { ForgotPassword } from "./pages/ForgotPassword";
import { Grants } from "./pages/Grants";
import { Install } from "./pages/Install";
import { Landing } from "./pages/Landing";
import { Library } from "./pages/Library";
import { LinkReader } from "./pages/LinkReader";
import { Login } from "./pages/Login";
import { Reader } from "./pages/Reader";
import { Privacy } from "./pages/Privacy";
import { RequestAccess } from "./pages/RequestAccess";
import { Terms } from "./pages/Terms";
import { ResetPassword } from "./pages/ResetPassword";
import { ShareLink } from "./pages/ShareLink";
import { Upload } from "./pages/Upload";

const HANDLE = /^@([a-z0-9](?:[a-z0-9._-]{1,28}[a-z0-9]))$/i;

/** podeabrir.com/@nome: a reader page bound to that personal address. Anything else goes home. */
function SlugRoute() {
  const { slug = "" } = useParams();
  const match = HANDLE.exec(decodeURIComponent(slug));
  return match ? <Reader key={match[1]} handle={match[1].toLowerCase()} /> : <Navigate to="/" replace />;
}

export function App() {
  return (
    <SessionProvider>
      <VaultProvider>
        <DocumentsProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<Landing />} />
                <Route path="entrar/" element={<Login />} />
                <Route path="cadastro/" element={<Enroll />} />
                <Route path="esqueci-senha/" element={<ForgotPassword />} />
                <Route path="solicitar-acesso/" element={<RequestAccess />} />
                <Route path="privacidade/" element={<Privacy />} />
                <Route path="termos/" element={<Terms />} />
                <Route path="redefinir-senha/" element={<ResetPassword />} />
                <Route path="ler/" element={<Reader />} />
                <Route path="instalar/" element={<Install />} />
                <Route path="s/:linkId" element={<LinkReader />} />
                <Route path="documentos/" element={<RequireOwner><Library /></RequireOwner>} />
                <Route path="documentos/:documentId/" element={<RequireOwner><DocumentViewer /></RequireOwner>} />
                <Route path="enviar/" element={<RequireOwner><Upload /></RequireOwner>} />
                <Route path="autorizar/" element={<RequireOwner><Approve /></RequireOwner>} />
                <Route path="autorizar/pedido/:grantId" element={<RequireOwner><Approve /></RequireOwner>} />
                <Route path="compartilhar/" element={<RequireOwner><ShareLink /></RequireOwner>} />
                <Route path="compartilhamentos/" element={<RequireOwner><Grants /></RequireOwner>} />
                <Route path="conta/" element={<RequireOwner><Account /></RequireOwner>} />
                <Route path="administracao/" element={<RequireOwner staff><Admin /></RequireOwner>} />
                <Route path="convites/" element={<Navigate to="/administracao/" replace />} />
                <Route path="consultorio/" element={<Navigate to="/ler/" replace />} />
                <Route path="exames/" element={<Navigate to="/documentos/" replace />} />
                <Route path="acessos/" element={<Navigate to="/compartilhamentos/" replace />} />
                <Route path=":slug" element={<SlugRoute />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </DocumentsProvider>
      </VaultProvider>
    </SessionProvider>
  );
}
