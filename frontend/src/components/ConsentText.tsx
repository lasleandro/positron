import { Link } from "react-router";

/** Specific, highlighted consent for sensitive data (LGPD art. 11, I) plus Terms/Privacy acceptance. */
export function ConsentText() {
  return (
    <span>
      Li e aceito os <Link to="/termos/" target="_blank">Termos de Uso</Link> e a{" "}
      <Link to="/privacidade/" target="_blank">Política de Privacidade</Link>, e <strong>autorizo o tratamento dos
      meus dados pessoais, inclusive sensíveis</strong> (como exames de saúde), para guardar e compartilhar documentos
      conforme as minhas escolhas.
    </span>
  );
}
