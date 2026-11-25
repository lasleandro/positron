import { Link } from "react-router";

import { CONTACT_EMAIL } from "../lib/brand";
import { useSession } from "../lib/session";

/**
 * Política de Privacidade e de Cookies. Reflects what the code does (docs/privacy_lgpd_2026-11-25.md).
 * Bracketed fields are company data to be completed and reviewed by legal counsel before launch.
 */
export function Privacy() {
  const { session } = useSession();
  return (
    <article className="legal narrow">
      <p className="eyebrow">Versão {session.legal_version}</p>
      <h1>Política de Privacidade</h1>
      <p className="lead">
        O pode abrir foi feito para que nem nós consigamos ler seus documentos. Esta política explica, em linguagem
        direta, quais dados tratamos, por quê, por quanto tempo e como você exerce seus direitos pela Lei Geral de
        Proteção de Dados (LGPD, Lei nº 13.709/2018).
      </p>

      <h2>1. Quem é o controlador</h2>
      <p>
        [Razão social], CNPJ [00.000.000/0000-00], com sede em [endereço] ("pode abrir"). Encarregado pelo tratamento de
        dados pessoais (DPO): [nome do encarregado], pelo e-mail <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>2. Que dados tratamos</h2>
      <ul>
        <li><strong>Conta:</strong> seu e-mail; uma credencial derivada da sua senha no seu dispositivo (nunca a senha); o segredo do autenticador, guardado cifrado; e cópias seladas da chave do seu cofre, que só abrem no seu dispositivo.</li>
        <li><strong>Documentos:</strong> o arquivo, o nome e o emissor são cifrados no seu dispositivo antes do envio. Não temos a chave para lê-los. A data do documento fica legível, para ordenar a lista.</li>
        <li><strong>Compartilhamentos e histórico ("Quem viu"):</strong> quando, por qual canal, por quanto tempo, quantas aberturas e a família do navegador de quem abriu (por exemplo, "Chrome · Windows"). O histórico não guarda endereço IP.</li>
        <li><strong>Endereço pessoal (@nome) e notificações:</strong> o endereço que você escolher e, se ativar, o identificador técnico de notificação do seu navegador.</li>
        <li><strong>Solicitações de acesso:</strong> e-mail, nome e mensagem que você enviar pelo formulário.</li>
        <li><strong>Registros de segurança:</strong> data, hora, ação e endereço IP de operações sensíveis (entrar, criar conta, compartilhar), para prevenir fraudes e cumprir a lei.</li>
      </ul>

      <h2>3. Para que usamos e com qual base legal</h2>
      <ul>
        <li><strong>Prestar o serviço que você contratou</strong> (conta, cofre, compartilhamentos): execução de contrato (art. 7º, V).</li>
        <li><strong>Guardar e compartilhar documentos que podem conter dados sensíveis</strong>, como exames de saúde: seu consentimento específico e destacado, dado ao criar a conta (art. 11, I). Você pode revogá-lo a qualquer momento (seção 8).</li>
        <li><strong>Segurança, prevenção a fraudes e proteção da sua conta</strong> (autenticador, limites de tentativas, histórico encadeado): legítimo interesse e garantia da prevenção à fraude e à segurança do titular (arts. 7º, IX, e 11, II, "g").</li>
        <li><strong>Guarda de registros de acesso</strong> por 6 meses: obrigação legal do Marco Civil da Internet (Lei nº 12.965/2014, art. 15).</li>
        <li><strong>E-mails transacionais</strong> (convite, redefinição de senha, avisos de pedido de leitura) e <strong>resposta às solicitações de acesso</strong>: execução de contrato e procedimentos preliminares a ele (art. 7º, V).</li>
      </ul>
      <p>Não vendemos dados, não usamos seus dados para publicidade e não fazemos perfis.</p>

      <h2>4. Com quem compartilhamos</h2>
      <ul>
        <li><strong>Com quem você autorizar</strong>, pelo tempo e com as regras que você escolher. A pessoa lê no navegador dela; o servidor não recebe a chave.</li>
        <li><strong>Operadores que nos ajudam a operar o serviço:</strong> Microsoft Azure (hospedagem e banco de dados, região [região]); GoDaddy (envio de e-mails transacionais); e os serviços de notificação do seu navegador (Google, Apple ou Mozilla), que recebem só um aviso genérico e cifrado, sem nomes de documentos.</li>
        <li><strong>Autoridades</strong>, quando houver ordem judicial ou obrigação legal.</li>
      </ul>
      <p>Alguns operadores podem processar dados fora do Brasil, com as garantias do art. 33 da LGPD (cláusulas contratuais e padrões de segurança).</p>

      <h2 id="cookies">5. Cookies e armazenamento no navegador</h2>
      <p>
        Usamos apenas cookies <strong>estritamente necessários</strong> para o serviço funcionar e ser seguro. Não usamos
        cookies de publicidade, de análise de audiência nem de terceiros. Por isso eles não dependem de consentimento,
        mas você pode bloqueá-los no navegador (o serviço deixará de funcionar).
      </p>
      <div className="table-scroll">
        <table className="legal-table">
          <thead><tr><th scope="col">Nome</th><th scope="col">Para que serve</th><th scope="col">Duração</th></tr></thead>
          <tbody>
            <tr><td><code>owner_session</code></td><td>Manter você conectado à sua conta</td><td>Até 4 horas</td></tr>
            <tr><td><code>csrf</code></td><td>Proteger formulários contra requisições forjadas</td><td>Até 1 ano</td></tr>
            <tr><td><code>reader_session</code></td><td>Ligar a tela de leitura (presencial ou @nome) ao acesso autorizado</td><td>Até o fim do acesso (máximo 7 dias)</td></tr>
            <tr><td><code>link_…</code></td><td>Sessão de leitura de um link compartilhado</td><td>Até 30 minutos</td></tr>
          </tbody>
        </table>
      </div>
      <p>
        No <strong>armazenamento local</strong> do navegador guardamos só preferências: se você já viu este aviso, se
        adiou a instalação do app e o último registro conferido do seu histórico. Na <strong>sessão da aba</strong>
        ficam a chave do seu cofre e chaves temporárias de leitura, apagadas quando a aba é fechada. O app instalado
        guarda apenas uma página "sem conexão", sem dados.
      </p>

      <h2>6. Por quanto tempo guardamos</h2>
      <ul>
        <li>Conta, documentos e histórico: enquanto a conta existir, ou até você excluí-los.</li>
        <li>Compartilhamentos encerrados, convites e links de redefinição expirados: apagados 1 dia depois de expirar (o registro no histórico permanece).</li>
        <li>Registros de acesso e de segurança: 6 meses.</li>
        <li>Solicitações de acesso: [prazo], ou até você pedir a exclusão.</li>
      </ul>

      <h2>7. Como protegemos</h2>
      <p>
        Cifragem nas pontas (AES-256-GCM, chaves derivadas no seu dispositivo), conexão TLS, autenticação em dois
        fatores, acessos com prazo e histórico encadeado verificável. Detalhes na seção "Tecniquês" da{" "}
        <Link to="/">página inicial</Link>. Nenhuma medida é infalível: guarde sua senha e seu código de recuperação.
        Sem eles, nem nós conseguimos recuperar seus documentos.
      </p>

      <h2>8. Seus direitos</h2>
      <p>
        Você pode pedir: confirmação e acesso aos seus dados, correção, anonimização, bloqueio ou eliminação de dados
        desnecessários, portabilidade, informação sobre com quem compartilhamos, eliminação dos dados tratados com
        consentimento e a revogação do consentimento (arts. 18 e 8º, § 5º). Escreva para{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>; respondemos em até 15 dias. Você também pode excluir
        documentos e encerrar compartilhamentos a qualquer momento no app, e reclamar à Autoridade Nacional de Proteção
        de Dados (ANPD).
      </p>

      <h2>9. Mudanças nesta política</h2>
      <p>
        Avisaremos no app e pediremos um novo aceite quando houver mudança relevante. Esta é a versão{" "}
        {session.legal_version}. Veja também os <Link to="/termos/">Termos de Uso</Link>.
      </p>
    </article>
  );
}
