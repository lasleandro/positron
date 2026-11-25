export function Alert({ message }: { message: string }) {
  return message ? <p className="alert" role="alert">{message}</p> : null;
}
