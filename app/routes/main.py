from flask import (Blueprint, Response, current_app, g, redirect, render_template,
                   request, send_from_directory, session, url_for)

from app.agenda import concluir_aulas_passadas, hoje
from app.consultas import ORDEM_RELEVANCIA, SELECT_AULAS, SELECT_INSTRUTORES
from app.sessao import exige_login
from database.db import get_connection

main_bp = Blueprint("main", __name__)

# Perfis não verificados também aparecem, mas depois dos verificados e com um selo
# "Em análise" no cartão. Se ficassem escondidos, quem acabou de se cadastrar como
# instrutor não se veria em lugar nenhum do site.
CONSULTA_DESTAQUES = SELECT_INSTRUTORES + f" WHERE i.ativo = 1 GROUP BY i.id ORDER BY {ORDEM_RELEVANCIA} LIMIT 6"

CONSULTA_RESUMO_INSTRUTOR = """
    SELECT i.id,
           i.verificado,
           i.ativo,
           i.valor_aula,
           ROUND(AVG(av.nota), 1) AS media_estrelas,
           COUNT(av.id)           AS total_avaliacoes,
           (SELECT COUNT(*) FROM agendamentos
             WHERE instrutor_id = i.id AND status = 'concluido') AS aulas_concluidas,
           (SELECT COUNT(*) FROM agendamentos
             WHERE instrutor_id = i.id AND status = 'agendado') AS aguardando_confirmacao
    FROM instrutores i
    LEFT JOIN avaliacoes av ON av.instrutor_id = i.id AND av.oculta = 0
    WHERE i.usuario_id = ?
    GROUP BY i.id
"""

PAGINAS_PUBLICAS = ("main.splash", "auth.login", "auth.cadastro_tipo")


@main_bp.route("/")
def splash():
    if session.get("usuario_id"):
        return redirect(url_for("main.home"))

    conexao = get_connection()
    numeros = conexao.execute(
        """
        SELECT (SELECT COUNT(*) FROM instrutores WHERE ativo = 1)   AS instrutores,
               (SELECT COUNT(*) FROM instrutores WHERE ativo = 1 AND (atende_libras = 1
                   OR atende_pcd = 1 OR veiculo_adaptado_disponivel = 1)) AS inclusivos,
               (SELECT COUNT(*) FROM avaliacoes WHERE oculta = 0)    AS avaliacoes
        """
    ).fetchone()

    # A prévia do hero mostra um instrutor DE VERDADE (o mais bem avaliado entre os
    # verificados) e um total calculado com preços reais, nunca dados inventados.
    vitrine = conexao.execute(
        SELECT_INSTRUTORES + f" WHERE i.ativo = 1 AND i.verificado = 1 GROUP BY i.id ORDER BY {ORDEM_RELEVANCIA} LIMIT 1"
    ).fetchone()
    veiculo = None
    if vitrine:
        veiculo = conexao.execute(
            """SELECT v.marca, v.modelo, v.valor_locacao FROM veiculos v
               JOIN instrutor_veiculos iv ON iv.veiculo_id = v.id
               WHERE iv.instrutor_id = ?
               ORDER BY (v.categoria_cnh != 'B'), v.valor_locacao LIMIT 1""",  # carro antes de moto
            (vitrine["id"],),
        ).fetchone()
    conexao.close()
    return render_template("splash.html", numeros=numeros, vitrine=vitrine, veiculo_vitrine=veiculo)


@main_bp.route("/service-worker.js")
def service_worker():
    # Servido da raiz (e não de /static/) porque o escopo de um service worker é
    # a pasta de onde ele vem: de /static/ ele só controlaria /static/*.
    resposta = send_from_directory(current_app.static_folder, "service-worker.js")
    resposta.headers["Service-Worker-Allowed"] = "/"
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@main_bp.route("/favicon.ico")
def favicon():
    # Navegadores pedem /favicon.ico por conta própria, mesmo com <link rel="icon">.
    # Sem esta rota, cada página gerava um 404 a mais no servidor.
    resposta = send_from_directory(current_app.static_folder, "icons/icone-192.png", mimetype="image/png")
    resposta.headers["Cache-Control"] = "public, max-age=604800"
    return resposta


@main_bp.route("/offline")
def offline():
    return render_template("offline.html")


@main_bp.route("/robots.txt")
def robots():
    linhas = [
        "User-agent: *",
        "Allow: /$",
        "Allow: /login",
        "Allow: /cadastro$",
        # Áreas que dependem de login não têm conteúdo útil para buscadores.
        "Disallow: /home",
        "Disallow: /busca",
        "Disallow: /instrutor/",
        "Disallow: /agendamento/",
        "Disallow: /minhas-aulas",
        "Disallow: /perfil",
        "Disallow: /cadastro/",
        "Disallow: /logout",
        f"Sitemap: {url_for('main.sitemap', _external=True)}",
    ]
    return Response("\n".join(linhas) + "\n", mimetype="text/plain")


@main_bp.route("/sitemap.xml")
def sitemap():
    urls = "".join(
        f"<url><loc>{url_for(pagina, _external=True)}</loc></url>" for pagina in PAGINAS_PUBLICAS
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
    return Response(xml, mimetype="application/xml")


@main_bp.route("/home")
@exige_login()
def home():
    usuario = g.usuario
    if usuario["tipo"] == "gerente":
        return redirect(url_for("gerencia.painel"))

    conexao = get_connection()
    concluir_aulas_passadas(conexao)

    contexto = {"usuario": usuario}

    if usuario["tipo"] == "candidato":
        contexto["instrutores"] = conexao.execute(CONSULTA_DESTAQUES).fetchall()
        contexto["salvos"] = conexao.execute(
            SELECT_INSTRUTORES + f"""
            JOIN favoritos f ON f.instrutor_id = i.id AND f.usuario_id = ?
            WHERE i.ativo = 1 GROUP BY i.id ORDER BY MAX(f.criado_em) DESC LIMIT 6
            """,
            (usuario["id"],),
        ).fetchall()
        contexto["proximas"] = conexao.execute(
            SELECT_AULAS + """
            WHERE ag.candidato_id = ? AND ag.status IN ('agendado', 'confirmado')
            ORDER BY ag.data, ag.horario LIMIT 2
            """,
            (usuario["id"],),
        ).fetchall()
        contexto["para_avaliar"] = conexao.execute(
            SELECT_AULAS + """
            WHERE ag.candidato_id = ? AND ag.status = 'concluido' AND av.id IS NULL
            ORDER BY ag.data DESC LIMIT 2
            """,
            (usuario["id"],),
        ).fetchall()
    else:
        contexto["resumo"] = conexao.execute(CONSULTA_RESUMO_INSTRUTOR, (usuario["id"],)).fetchone()
        contexto["agenda"] = conexao.execute(
            SELECT_AULAS + """
            WHERE i.usuario_id = ? AND ag.status IN ('agendado', 'confirmado') AND ag.data >= ?
            ORDER BY ag.data, ag.horario LIMIT 5
            """,
            (usuario["id"], hoje().isoformat()),
        ).fetchall()

    conexao.close()
    return render_template("home.html", **contexto)


@main_bp.app_context_processor
def dados_de_navegacao():
    """Disponível em todo template: destino da navegação e indexação da página."""
    return {
        "pagina_publica": request.endpoint in PAGINAS_PUBLICAS,
        "url_canonica": request.base_url,
    }
