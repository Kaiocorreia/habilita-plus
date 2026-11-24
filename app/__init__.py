import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app.agenda import data_por_extenso, formatar_moeda
from app.configuracoes import configuracoes
from database.migrar import migrar
from app.seguranca import aplicar_cabecalhos, token_csrf, verificar_csrf


def _ligado(nome, padrao):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes")


def create_app():
    app = Flask(__name__)

    # Sem a variável de ambiente, gera uma chave aleatória a cada início: as sessões
    # não sobrevivem a um restart, mas nunca ficam previsíveis (o que permitiria
    # forjar o cookie de login de qualquer usuário).
    chave_configurada = os.environ.get("HABILITA_SECRET_KEY")
    app.config["SECRET_KEY"] = chave_configurada or secrets.token_hex(32)

    # Em produção (onde a chave é configurada) o site roda em HTTPS, então o cookie
    # de sessão só trafega criptografado. Localmente, em http, isso o impediria de
    # funcionar; HABILITA_COOKIE_SEGURO sobrepõe a detecção se for preciso.
    https = _ligado("HABILITA_COOKIE_SEGURO", padrao=bool(chave_configurada))
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=https,
        # Arquivos estáticos ficam em cache por 7 dias; CSS e JS levam ?v= com a
        # data de modificação, então uma nova versão é baixada na hora.
        SEND_FILE_MAX_AGE_DEFAULT=7 * 24 * 3600,
        MAX_CONTENT_LENGTH=64 * 1024,
    )

    # O PythonAnywhere termina o HTTPS num proxy e repassa a requisição em http.
    # ProxyFix lê o cabeçalho X-Forwarded-Proto para gerar URLs absolutas corretas.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.before_request(verificar_csrf)
    app.after_request(lambda resposta: aplicar_cabecalhos(resposta, https))

    # Atualiza a estrutura do banco se o código novo precisar (com cópia de
    # segurança antes). Assim, publicar é só "git pull + Reload": não há passo
    # manual para esquecer. Num banco já atualizado, só confere e segue.
    feito = migrar(silencioso=True)
    if feito:
        app.logger.warning("Banco migrado: %s", "; ".join(feito))

    _registrar_templates(app)
    _registrar_erros(app)

    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.busca import busca_bp
    from app.routes.instrutores import instrutores_bp
    from app.routes.agendamentos import agendamentos_bp
    from app.routes.avaliacoes import avaliacoes_bp
    from app.routes.gerencia import gerencia_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(busca_bp)
    app.register_blueprint(instrutores_bp)
    app.register_blueprint(agendamentos_bp)
    app.register_blueprint(avaliacoes_bp)
    app.register_blueprint(gerencia_bp)

    @app.context_processor
    def aviso_da_gerencia():
        # O aviso geral aparece no topo de todas as páginas enquanto estiver ativo.
        dados = configuracoes()
        return {"aviso_geral": dados["aviso_texto"] if dados["aviso_ativo"] else None}

    return app


def _registrar_templates(app):
    pasta_static = Path(app.static_folder)
    versoes = {}

    def asset(caminho):
        """URL de um arquivo estático com ?v= para invalidar o cache ao mudar."""
        if caminho not in versoes or app.debug:
            arquivo = pasta_static / caminho
            versoes[caminho] = int(arquivo.stat().st_mtime) if arquivo.exists() else 0
        return url_for("static", filename=caminho, v=versoes[caminho])

    def link_whatsapp(telefone):
        """Link wa.me para o telefone cadastrado (DDD + número), ou None se ausente."""
        digitos = "".join(c for c in (telefone or "") if c.isdigit())
        return f"https://wa.me/55{digitos}" if len(digitos) in (10, 11) else None

    def primeiro_nome(nome):
        return (nome or "").split()[0] if (nome or "").split() else ""

    app.jinja_env.globals.update(csrf_token=token_csrf, asset=asset)
    app.jinja_env.filters.update(moeda=formatar_moeda, whatsapp=link_whatsapp,
                                 primeiro_nome=primeiro_nome, extenso=data_por_extenso)


def _registrar_erros(app):
    mensagens = {
        404: ("Página não encontrada", "O endereço pode ter mudado ou não existir mais."),
        405: ("Ação não permitida", "Essa página não aceita esse tipo de acesso."),
        413: ("Envio grande demais", "Os dados enviados passaram do limite permitido."),
        500: ("Algo deu errado do nosso lado", "Já registramos o problema. Tente de novo em instantes."),
    }

    def pagina_erro(codigo):
        titulo, texto = mensagens[codigo]
        return render_template("erro.html", codigo=codigo, titulo=titulo, texto=texto), codigo

    @app.errorhandler(400)
    def requisicao_invalida(erro):
        if getattr(erro, "description", "") == "csrf":
            # Na prática quase sempre é uma aba aberta há muito tempo, ou um
            # formulário enviado depois do servidor reiniciar.
            flash("Sua sessão expirou. Confira os dados e tente de novo.", "erro")
            return redirect(_voltar_com_seguranca())
        return render_template(
            "erro.html", codigo=400, titulo="Requisição inválida",
            texto="Os dados enviados não puderam ser processados.",
        ), 400

    for codigo in mensagens:
        app.register_error_handler(codigo, lambda erro, codigo=codigo: pagina_erro(codigo))


def _voltar_com_seguranca():
    """Volta para a página anterior só se ela for do próprio site."""
    origem = request.referrer
    if origem:
        alvo = urlparse(origem)
        if alvo.netloc == request.host:
            return alvo.path + (f"?{alvo.query}" if alvo.query else "")
    return url_for("main.splash")
