import { Bell, Check, Download, EllipsisVertical, Share, SquarePlus } from "lucide-react";
import { Link } from "react-router";

import { isIos, useInstallPrompt } from "../lib/pwa";

/** How to install: one tap on Android/Chromium, Share -> Add to Home Screen on iPhone/iPad. */
export function Install() {
  const { status, promptInstall } = useInstallPrompt();
  const ios = isIos();
  return (
    <div className="narrow">
      <div className="page-heading install-heading">
        <img src="/icon-192.png" alt="" width={56} height={56} />
        <div><h1>Instalar o app</h1><p className="muted">Abra o pode abrir pela tela inicial, como um aplicativo.</p></div>
      </div>
      {status === "installed" ? (
        <section className="surface form-card">
          <h2><Check size={18} aria-hidden="true" /> App instalado</h2>
          <p className="muted">Você já está usando o pode abrir como aplicativo.</p>
          <p className="route-link"><Link to="/conta/">Ativar notificações em Conta</Link></p>
        </section>
      ) : ios ? (
        <section className="surface form-card">
          <h2>No iPhone ou iPad</h2>
          <ol className="install-steps">
            <li><Share size={18} aria-hidden="true" /><span>Abra este site no <strong>Safari</strong> e toque em <strong>Compartilhar</strong>.</span></li>
            <li><SquarePlus size={18} aria-hidden="true" /><span>Escolha <strong>Adicionar à Tela de Início</strong>.</span></li>
            <li><Check size={18} aria-hidden="true" /><span>Toque em <strong>Adicionar</strong>.</span></li>
            <li><Bell size={18} aria-hidden="true" /><span>Abra o app pela tela inicial e ative as notificações em <strong>Conta</strong> (iOS 16.4 ou superior).</span></li>
          </ol>
        </section>
      ) : status === "available" ? (
        <section className="surface form-card">
          <h2><Download size={18} aria-hidden="true" /> Instalação com um toque</h2>
          <p className="muted">Seu navegador pode instalar o app agora.</p>
          <div className="actions"><button className="button primary" onClick={() => void promptInstall()}><Download size={16} aria-hidden="true" />Instalar o app</button></div>
        </section>
      ) : (
        <section className="surface form-card">
          <h2>Pelo menu do navegador</h2>
          <ol className="install-steps">
            <li><EllipsisVertical size={18} aria-hidden="true" /><span>Abra o menu do navegador (⋮ ou ⋯).</span></li>
            <li><SquarePlus size={18} aria-hidden="true" /><span>Escolha <strong>Instalar app</strong> ou <strong>Adicionar à tela inicial</strong>.</span></li>
          </ol>
          <p className="muted">Se a opção não aparecer, navegue um pouco pelo site e tente de novo.</p>
        </section>
      )}
    </div>
  );
}
