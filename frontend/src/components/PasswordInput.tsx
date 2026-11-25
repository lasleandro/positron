import { Eye, EyeOff } from "lucide-react";
import { useState, type InputHTMLAttributes } from "react";

/** Password field with a show/hide toggle. Accepts every normal input prop except `type`. */
export function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-field">
      <input {...props} type={visible ? "text" : "password"} spellCheck={false} autoCapitalize="none" />
      <button type="button" className="password-toggle" onClick={() => setVisible(!visible)}
        aria-label={visible ? "Ocultar senha" : "Mostrar senha"} aria-pressed={visible}
        aria-controls={props.id} title={visible ? "Ocultar senha" : "Mostrar senha"}>
        {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
      </button>
    </div>
  );
}
