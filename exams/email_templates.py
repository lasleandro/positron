"""Escaped multipart security emails (structure ported from agenda_ai, Pode Abrir branding)."""

from html import escape

from .mailer import OutboundEmail

BRAND = "Pode Abrir"


def _message(to: str, subject: str, paragraphs: list[str], action: tuple[str, str] | None = None) -> OutboundEmail:
    action_html = action_text = ""
    if action:
        label, url = action
        action_html = (
            f'<p style="margin:28px 0;"><a href="{escape(url, quote=True)}" style="display:inline-block;'
            'padding:12px 22px;background:#1d1d1b;color:#ffffff;border-radius:999px;text-decoration:none;'
            f'font-weight:600;">{escape(label)}</a></p>'
        )
        action_text = f"\n{label}: {url}\n"
    body_html = "".join(f"<p>{escape(text)}</p>" for text in paragraphs)
    html = (
        '<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f4f2ed;'
        'font-family:Helvetica,Arial,sans-serif;color:#1d1d1b;"><main style="max-width:560px;margin:32px auto;'
        'padding:32px;background:#fdfcfa;border:1px solid #dcd8cf;border-radius:14px;">'
        f'<h1 style="font-size:22px;margin:0 0 16px;">{escape(subject)}</h1>'
        f'<div style="font-size:16px;line-height:1.6;">{body_html}</div>{action_html}'
        f'<p style="margin-top:28px;font-size:13px;color:#6b6963;">{BRAND}</p></main></body></html>'
    )
    text = f"{subject}\n\n" + "\n\n".join(paragraphs) + f"\n{action_text}\n{BRAND}"
    return OutboundEmail(to, subject, html, text)


def invitation_email(to: str, url: str, hours: int) -> OutboundEmail:
    return _message(to, "Seu convite para o Pode Abrir", [
        f"Você recebeu um convite para guardar e compartilhar documentos com segurança, vinculado a {to}.",
        f"O link é de uso único e expira em {hours} horas. Seus documentos serão cifrados no seu "
        "próprio dispositivo antes do envio.",
        "Se você não esperava este convite, ignore esta mensagem.",
    ], ("Criar minha conta", url))


def password_reset_email(to: str, url: str, minutes: int) -> OutboundEmail:
    return _message(to, "Redefina sua senha do Pode Abrir", [
        f"Recebemos uma solicitação para redefinir a senha da conta {to}. Este link expira em {minutes} minutos.",
        "Para manter seus documentos, tenha em mãos o código de recuperação que você guardou no cadastro "
        "e o seu aplicativo autenticador.",
        "Se não foi você, ignore esta mensagem. Sua senha permanecerá inalterada.",
    ], ("Redefinir senha", url))


def password_changed_email(to: str) -> OutboundEmail:
    return _message(to, "Sua senha foi alterada", [
        f"A senha da conta {to} foi alterada e as sessões abertas foram encerradas.",
        "Se você não fez essa alteração, entre em contato com o suporte imediatamente.",
    ])


def read_request_email(to: str, url: str) -> OutboundEmail:
    return _message(to, "Pedido de leitura dos seus documentos", [
        "Alguém abriu o seu endereço pessoal no Pode Abrir e pediu para ler documentos agora.",
        "Nada é liberado sem a sua aprovação. Confira se o código de 6 dígitos no seu celular é o mesmo "
        "da tela de quem pediu antes de aprovar. O pedido expira em poucos minutos.",
        "Se você não reconhece este pedido, ignore-o ou desative o endereço pessoal em Conta.",
    ], ("Ver pedido", url))
