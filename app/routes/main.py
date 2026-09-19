from flask import Blueprint, current_app, redirect, render_template, send_from_directory, session, url_for

from database.db import get_connection

main_bp = Blueprint("main", __name__)

CONSULTA_INSTRUTORES = """
    SELECT i.id,
           u.nome,
           u.cidade,
           u.foto_url,
           i.categorias_cnh,
           i.valor_aula,
           i.regiao_atuacao,
           i.verificado,
           i.atende_libras,
           i.somente_mulheres,
           i.atende_neurodivergentes,
           i.atende_pcd,
           i.veiculo_adaptado_disponivel,
           ROUND(AVG(a.nota), 1) AS media_estrelas,
           COUNT(a.id)           AS total_avaliacoes
    FROM instrutores i
    JOIN usuarios u ON u.id = i.usuario_id
    LEFT JOIN avaliacoes a ON a.instrutor_id = i.id
    WHERE i.verificado = 1
    GROUP BY i.id
    ORDER BY (media_estrelas IS NULL), media_estrelas DESC, total_avaliacoes DESC
    LIMIT 5
"""


CONSULTA_MINHAS_AULAS = """
    SELECT ag.id,
           ag.horario,
           ag.status,
           ag.valor,
           ag.valor_locacao,
           strftime('%d/%m/%Y', ag.data) AS data_formatada,
           u.nome  AS nome_instrutor,
           u.foto_url,
           i.id    AS instrutor_id,
           av.id   AS avaliacao_id
    FROM agendamentos ag
    JOIN instrutores i ON i.id = ag.instrutor_id
    JOIN usuarios u ON u.id = i.usuario_id
    LEFT JOIN avaliacoes av ON av.agendamento_id = ag.id
    WHERE ag.candidato_id = ?
    ORDER BY ag.data DESC
    LIMIT 5
"""


@main_bp.route("/")
def splash():
    return render_template("splash.html")


@main_bp.route("/service-worker.js")
def service_worker():
    resposta = send_from_directory(current_app.static_folder, "service-worker.js")
    resposta.headers["Service-Worker-Allowed"] = "/"
    return resposta


@main_bp.route("/home")
def home():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    conexao = get_connection()
    usuario = conexao.execute(
        "SELECT nome, tipo, cidade FROM usuarios WHERE id = ?",
        (session["usuario_id"],),
    ).fetchone()

    # O cookie pode apontar para um usuário que não existe mais (conta apagada ou
    # banco recriado, o que muda os IDs). Sem isso, o template quebraria com 500.
    if usuario is None:
        conexao.close()
        session.clear()
        return redirect(url_for("auth.login"))

    instrutores = conexao.execute(CONSULTA_INSTRUTORES).fetchall()

    minhas_aulas = []
    if usuario["tipo"] == "candidato":
        minhas_aulas = conexao.execute(CONSULTA_MINHAS_AULAS, (session["usuario_id"],)).fetchall()

    conexao.close()

    return render_template(
        "home.html",
        usuario=usuario,
        instrutores=instrutores,
        minhas_aulas=minhas_aulas,
    )
