import {
  AtSign, Briefcase, Calculator, Clock3, EyeOff, FileLock2, GraduationCap, House, Link2, Mail,
  MonitorSmartphone, Plane, Scale, ShieldCheck, Stethoscope, Timer,
} from "lucide-react";
import { Link } from "react-router";

import flowDesktop from "../../assets/pode-abrir-diagrama/fluxo-desktop.svg";
import flowMobile from "../../assets/pode-abrir-diagrama/fluxo-mobile.svg";
import symbol from "../../assets/svg/pode-abrir-simbolo-grafite.svg";
import { CONTACT_EMAIL } from "../lib/brand";
import { useSession } from "../lib/session";

const PILLARS = [
  {
    icon: ShieldCheck, title: "Seguro de verdade",
    text: "Cada documento é cifrado no seu dispositivo antes de sair dele. O servidor guarda só dados ilegíveis, inclusive os nomes dos arquivos.",
  },
  {
    icon: EyeOff, title: "Privado por padrão",
    text: "Quem recebe só lê: sem download, com marca d’água e tempo contado. Você vê cada abertura e encerra quando quiser.",
  },
  {
    icon: Clock3, title: "Simples em segundos",
    text: "Mostre um QR, mande um link ou passe seu endereço @. Quem lê não precisa de conta nem de aplicativo.",
  },
];

const WAYS = [
  { icon: MonitorSmartphone, title: "Na hora, ao vivo", text: "A tela de quem vai ler mostra um QR (e um código para digitar, se preferir). Você escaneia, escolhe os documentos e o tempo. Ao sair, encerra pelo celular." },
  { icon: Link2, title: "Por link, como um snap", text: "Envie por WhatsApp ou e-mail um link que abre uma vez só ou por até 7 dias. Com PIN para vários documentos ou prazos longos." },
  { icon: AtSign, title: "Pelo seu endereço", text: "podeabrir.com/@voce: quem abre pede acesso, e você aprova no celular conferindo um código de 6 dígitos." },
];

const STANDARDS = ["AES-256-GCM", "ECDH P-256", "PBKDF2-SHA-256 + HKDF", "SHA-256 encadeado", "TOTP (RFC 6238)", "TLS 1.2+", "Web Crypto API"];

const USE_CASES = [
  { icon: Stethoscope, title: "Consultas médicas", text: "Exames e laudos de vários laboratórios abertos na tela do médico, só durante a consulta." },
  { icon: House, title: "Aluguel de imóvel", text: "Holerite, declaração de IR e comprovantes para a imobiliária, sem cópias circulando." },
  { icon: Briefcase, title: "Admissão e RH", text: "Documentos pessoais para o RH conferir, com prazo para deixar de existir." },
  { icon: Calculator, title: "Contador e banco", text: "Extratos e declarações por um link que expira, com histórico de quem abriu." },
  { icon: Scale, title: "Advogados", text: "Contratos e peças para revisão com PIN, sem anexos esquecidos em caixas de e-mail." },
  { icon: Plane, title: "Viagens e vistos", text: "Passaporte e reservas à mão no balcão, sem deixar arquivos no computador de ninguém." },
  { icon: GraduationCap, title: "Escola e faculdade", text: "Históricos e certidões para matrícula, liberados só para quem precisa ver." },
];

export function Landing() {
  const { session } = useSession();
  return (
    <div className="landing">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Compartilhamento efêmero de documentos</p>
          <h1>Mostre o documento. Não entregue.</h1>
          <p className="lead">
            Guarde exames, contratos e documentos pessoais cifrados e libere a leitura por minutos, só para quem você
            escolher. Quando o tempo acaba, acabou.
          </p>
          <div className="actions">
            {session.user
              ? <Link className="button primary" to="/documentos/">Meus documentos</Link>
              : <Link className="button primary" to="/entrar/">Entrar</Link>}
            <Link className="button secondary" to="/ler/"><FileLock2 size={18} aria-hidden="true" />Ler documentos</Link>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <img className="hero-symbol" src={symbol} alt="" width={176} height={176} />
          <span className="hero-chip chip-read"><EyeOff size={14} />Somente leitura</span>
          <span className="hero-chip mock-timer"><Timer size={14} />Termina em 12:41</span>
        </div>
      </section>

      <section className="pillars">
        {PILLARS.map(({ icon: Icon, title, text }) => (
          <article key={title} className="pillar">
            <Icon size={24} aria-hidden="true" />
            <h2>{title}</h2>
            <p>{text}</p>
          </article>
        ))}
      </section>

      <section className="ways">
        <h2 className="section-title">Três jeitos de deixar abrir</h2>
        <ol className="steps surface">
          {WAYS.map(({ icon: Icon, title, text }, index) => (
            <li key={title}>
              <span className="step-index">{String(index + 1).padStart(2, "0")}</span>
              <Icon className="step-icon" size={22} aria-hidden="true" />
              <div><strong>{title}</strong><span>{text}</span></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="use-cases">
        <h2 className="section-title">Para qualquer documento que não deveria ficar por aí</h2>
        <div className="case-grid">
          {USE_CASES.map(({ icon: Icon, title, text }) => (
            <article key={title} className="case surface">
              <Icon size={22} aria-hidden="true" />
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="flow" aria-labelledby="flow-title">
        <h2 id="flow-title" className="section-title">Tecniquês, para quem gosta</h2>
        <picture className="flow-diagram">
          <source media="(max-width: 799px)" srcSet={flowMobile} width={375} height={457} />
          <img src={flowDesktop} width={1140} height={279} loading="lazy"
            alt="No seu dispositivo, o documento é criptografado antes do envio. O pode abrir guarda o arquivo cifrado e controla o acesso, sem a chave para ler o conteúdo. O documento é aberto no navegador de quem você autoriza, durante o prazo escolhido." />
        </picture>
        <ul className="standards" aria-label="Padrões criptográficos usados">
          {STANDARDS.map((name) => <li key={name}>{name}</li>)}
        </ul>
      </section>

      <section className="honest surface">
        <h2>Sem promessas impossíveis</h2>
        <p>
          Nenhum site consegue impedir uma foto da tela. Por isso o Pode Abrir trabalha com o que funciona: tempo curto,
          marca d’água com quem e quando, nada de download e um histórico verificável de cada abertura.
        </p>
      </section>

      <section className="contact surface">
        <div>
          <h2>Fale com a gente</h2>
          <p>Dúvidas, parcerias com clínicas, escritórios e empresas, ou um caso de uso que não está aqui.</p>
        </div>
        <a className="button primary" href={`mailto:${CONTACT_EMAIL}`}><Mail size={18} aria-hidden="true" />{CONTACT_EMAIL}</a>
      </section>

      {!session.user && (
        <p className="landing-invite">Ainda não tem conta? <Link to="/solicitar-acesso/">Solicite acesso</Link>. Recebeu um convite por e-mail? Abra o link recebido.</p>
      )}
    </div>
  );
}
