import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal confirmation for irreversible actions (native <dialog>: focus trap and Esc for free). */
export function ConfirmDialog({ open, title, children, confirmLabel, danger, onConfirm, onCancel }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);
  return (
    <dialog ref={dialog} className="vault-dialog" onCancel={(event) => { event.preventDefault(); onCancel(); }}>
      <h2>{title}</h2>
      <div className="muted confirm-body">{children}</div>
      <div className="actions">
        <button type="button" className={danger ? "button danger-solid" : "button primary"} onClick={onConfirm} autoFocus>
          {confirmLabel}
        </button>
        <button type="button" className="button ghost" onClick={onCancel}>Cancelar</button>
      </div>
    </dialog>
  );
}
