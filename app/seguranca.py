"""Proteções transversais: token CSRF e cabeçalhos HTTP de segurança.

Implementado com a biblioteca padrão para manter o projeto com uma única
dependência externa (Flask).
"""

import hmac
import secrets

from flask import abort, request, session

CAMPO_CSRF = "csrf_token"

# Política de conteúdo: só carrega recursos do próprio site. Isso exige que não
# exista nenhum <script> ou atributo style="" embutido nos templates.
POLITICA_CONTEUDO = "; ".join([
    "default-src 'self'",
    "img-src 'self' data:",
    "style-src 'self'",
    "script-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])


def token_csrf():
    """Token secreto por sessão. Vai em um campo oculto de todo formulário POST."""
    if CAMPO_CSRF not in session:
        session[CAMPO_CSRF] = secrets.token_urlsafe(32)
    return session[CAMPO_CSRF]


def verificar_csrf():
    """Recusa POSTs sem o token da sessão.

    Sem isso, um site malicioso poderia criar um formulário invisível que, ao ser
    aberto por alguém logado, cancela aulas ou faz agendamentos em nome dela.
    """
    if request.method != "POST":
        return

    enviado = request.form.get(CAMPO_CSRF, "")
    esperado = session.get(CAMPO_CSRF, "")
    # compare_digest leva o mesmo tempo para qualquer entrada, evitando que o
    # token seja descoberto medindo o tempo de resposta.
    if not esperado or not hmac.compare_digest(enviado, esperado):
        abort(400, description="csrf")


def aplicar_cabecalhos(resposta, https):
    cabecalhos = resposta.headers
    cabecalhos.setdefault("Content-Security-Policy", POLITICA_CONTEUDO)
    cabecalhos.setdefault("X-Content-Type-Options", "nosniff")
    cabecalhos.setdefault("X-Frame-Options", "DENY")
    cabecalhos.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    cabecalhos.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if https:
        cabecalhos.setdefault("Strict-Transport-Security", "max-age=31536000")

    # Páginas de quem está logado não podem ficar no cache: depois do logout, o
    # botão "voltar" do navegador mostraria dados da conta.
    if session.get("usuario_id") and not request.path.startswith("/static/"):
        cabecalhos["Cache-Control"] = "no-store"

    return resposta
