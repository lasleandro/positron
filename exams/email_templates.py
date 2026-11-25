"""Escaped multipart security emails (structure ported from agenda_ai, Pode Abrir branding)."""

from html import escape
from pathlib import Path

from django.conf import settings

from .mailer import InlineImage, OutboundEmail

BRAND = "Pode Abrir"


GRAFITE = "#2C2923"
MARFIM = "#FCEEDB"
CONTACT = settings.CONTACT_EMAIL
# The wordmark travels inside the message (cid:), so it shows wherever the email is opened,
# whatever server sent it, and without a remote-image request.
LOGO_CID = "logo@podeabrir.com"
LOGO = InlineImage(LOGO_CID, "pode-abrir.png", (Path(__file__).parent / "email_assets" / "logo.png").read_bytes())


def _message(to: str, subject: str, paragraphs: list[str], action: tuple[str, str] | None = None) -> OutboundEmail:
    action_html = action_text = ""
    if action:
        label, url = action
        action_html = (
            f'<p style="margin:28px 0;"><a href="{escape(url, quote=True)}" style="display:inline-block;'
            f'padding:12px 22px;background:{GRAFITE};color:#ffffff;border-radius:999px;text-decoration:none;'
            f'font-weight:600;">{escape(label)}</a></p>'
        )
        action_text = f"\n{label}: {url}\n"
    body_html = "".join(f"<p>{escape(text)}</p>" for text in paragraphs)
    html = (
        f'<!doctype html><html lang="pt-BR"><body style="margin:0;background:{MARFIM};'
        f'font-family:Helvetica,Arial,sans-serif;color:{GRAFITE};"><main style="max-width:560px;margin:32px auto;'
        'padding:32px;background:#fffdf9;border:1px solid #e7ddcc;border-radius:14px;">'
        f'<p style="margin:0 0 24px;"><img src="cid:{LOGO_CID}" width="160" height="35" alt="pode abrir" '
        f'style="display:block;border:0;font:600 20px Helvetica,Arial,sans-serif;color:{GRAFITE};"></p>'
        f'<h1 style="font-size:22px;margin:0 0 16px;">{escape(subject)}</h1>'
        f'<div style="font-size:16px;line-height:1.6;">{body_html}</div>{action_html}'
        f'<p style="margin-top:28px;font-size:13px;color:#6e6658;">{BRAND} · '
        f'<a href="mailto:{CONTACT}" style="color:#6e6658;">{CONTACT}</a></p></main></body></html>'
    )
    text = f"{subject}\n\n" + "\n\n".join(paragraphs) + f"\n{action_text}\n{BRAND} · {CONTACT}"
    return OutboundEmail(to, subject, html, text, images=(LOGO,))


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


def access_request_email(to: str, requester: str, name: str, message: str, when: str) -> OutboundEmail:
    """Internal notice to the team; replying answers the requester directly."""
    lines = [f"Nova solicitação de acesso recebida em {when}.", f"Email: {requester}"]
    if name:
        lines.append(f"Nome: {name}")
    lines.append(f"Mensagem: {message}" if message else "Sem mensagem.")
    lines.append("Responda este e-mail para falar com a pessoa. Para liberar, envie um convite em Conta → Convites.")
    email = _message(to, "Solicitação de acesso ao pode abrir", lines)
    return OutboundEmail(email.to_address, email.subject, email.html_body, email.text_body, reply_to=requester)
