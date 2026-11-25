import { Link } from "react-router";

import { CONTACT_EMAIL } from "../lib/brand";
import { useSession } from "../lib/session";

/** Termos de Uso. Bracketed fields are company data to be completed and reviewed by legal counsel. */
export function Terms() {
  const { session } = useSession();
  return (
    <article className="legal narrow">
      <p className="eyebrow">Versão {session.legal_version}</p>
      <h1>Termos de Uso</h1>
      <p className="lead">
        Ao criar uma conta ou ler documentos no pode abrir, você concorda com estes termos e com a{" "}
        <Link to="/privacidade/">Política de Privacidade</Link>.
      </p>

      <h2>1. O serviço</h2>
      <p>
        O pode abrir permite guardar documentos cifrados e liberar a leitura, por tempo limitado, a quem você escolher.
        O serviço é oferecido por [razão social], CNPJ [00.000.000/0000-00].
      </p>

      <h2>2. Sua conta</h2>
      <ul>
        <li>O cadastro é feito por convite enviado ao seu e-mail.</li>
        <li>Você é responsável pela sua senha, pelo seu autenticador e pelo seu <strong>código de recuperação</strong>. Como os documentos são cifrados no seu dispositivo, sem a senha ou o código de recuperação eles não podem ser recuperados, nem por nós.</li>
        <li>Avise-nos em <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> se suspeitar de uso indevido da sua conta.</li>
      </ul>

      <h2>3. Uso permitido</h2>
      <ul>
        <li>Guarde e compartilhe apenas documentos que você tem o direito de guardar e compartilhar.</li>
        <li>Ao compartilhar documentos com dados de outras pessoas, você é responsável por ter base legal para isso.</li>
        <li>É proibido usar o serviço para conteúdo ilícito, para burlar os limites de acesso ou para tentar acessar dados de terceiros.</li>
      </ul>

      <h2>4. Quem recebe acesso</h2>
      <p>
        Quem lê um documento pelo pode abrir deve usá-lo somente para a finalidade combinada com quem compartilhou. A
        marca d'água indica que a divulgação é proibida e que os dados são protegidos pela LGPD. O serviço não
        consegue impedir capturas ou fotos da tela; esse uso indevido é de responsabilidade de quem o fizer.
      </p>

      <h2>5. Disponibilidade e mudanças</h2>
      <p>
        Trabalhamos para manter o serviço disponível, mas ele pode ter interrupções para manutenção ou por fatores fora
        do nosso controle. Podemos alterar funcionalidades e estes termos; mudanças relevantes serão avisadas no app e
        exigirão novo aceite.
      </p>

      <h2>6. Encerramento</h2>
      <p>
        Você pode pedir o encerramento da conta a qualquer momento. Podemos suspender contas que violem estes termos.
        Após o encerramento, os dados são eliminados conforme a <Link to="/privacidade/">Política de Privacidade</Link>.
      </p>

      <h2>7. Lei e foro</h2>
      <p>Estes termos seguem as leis do Brasil. Fica eleito o foro da comarca de [cidade/UF], ressalvados os direitos do consumidor.</p>
    </article>
  );
}
