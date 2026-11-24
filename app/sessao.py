"""Controle de acesso às rotas que exigem login."""

from functools import wraps

from flask import flash, g, redirect, request, session, url_for

from database.db import get_connection


def iniciar_sessao(usuario):
    # Limpar antes de gravar evita "fixação de sessão": um cookie plantado por
    # terceiros antes do login não continua válido depois dele.
    session.clear()
    session["usuario_id"] = usuario["id"]
    session["usuario_nome"] = usuario["nome"]
    session["usuario_tipo"] = usuario["tipo"]


def exige_login(tipo=None):
    """Exige usuário logado e, opcionalmente, de um tipo ('candidato' ou 'instrutor').

    Também confere se o usuário ainda existe no banco. O cookie pode apontar para
    uma conta apagada (ou para um banco recriado, que muda os IDs); sem essa
    checagem, a tela quebraria com erro 500 ao tentar ler os dados dele.
    """
    def decorador(rota):
        @wraps(rota)
        def protegida(*args, **kwargs):
            usuario_id = session.get("usuario_id")
            if usuario_id is None:
                return redirect(url_for("auth.login", proximo=request.path))

            conexao = get_connection()
            usuario = conexao.execute(
                "SELECT id, nome, tipo, cidade FROM usuarios WHERE id = ?", (usuario_id,)
            ).fetchone()
            conexao.close()

            if usuario is None:
                session.clear()
                flash("Sua sessão não é mais válida. Entre novamente.", "erro")
                return redirect(url_for("auth.login"))

            if tipo and usuario["tipo"] != tipo:
                flash("Essa área não está disponível para o seu tipo de conta.", "erro")
                return redirect(url_for("main.home"))

            g.usuario = usuario
            return rota(*args, **kwargs)
        return protegida
    return decorador


def destino_seguro(caminho):
    """Aceita só caminhos internos, para o ?proximo= não virar redirecionamento aberto."""
    if caminho and caminho.startswith("/") and not caminho.startswith("//") and "\\" not in caminho:
        return caminho
    return url_for("main.home")
