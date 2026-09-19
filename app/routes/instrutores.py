from flask import Blueprint, abort, redirect, render_template, session, url_for

from database.db import get_connection

instrutores_bp = Blueprint("instrutores", __name__)

CONSULTA_PERFIL = """
    SELECT i.id,
           u.nome,
           u.cidade,
           u.telefone,
           u.foto_url,
           (SELECT GROUP_CONCAT(categoria)
              FROM (SELECT categoria FROM instrutor_categorias
                     WHERE instrutor_id = i.id ORDER BY categoria)) AS categorias_cnh,
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
    WHERE i.id = ?
    GROUP BY i.id
"""

CONSULTA_AVALIACOES = """
    SELECT av.nota,
           av.comentario,
           strftime('%d/%m/%Y', av.data) AS data_formatada,
           u.nome AS nome_candidato
    FROM avaliacoes av
    JOIN usuarios u ON u.id = av.candidato_id
    WHERE av.instrutor_id = ?
    ORDER BY av.data DESC
"""

CONSULTA_VEICULOS = """
    SELECT v.id,
           v.marca,
           v.modelo,
           v.categoria_cnh,
           v.transmissao,
           v.adaptado,
           v.valor_locacao,
           v.imagem
    FROM veiculos v
    JOIN instrutor_veiculos iv ON iv.veiculo_id = v.id
    WHERE iv.instrutor_id = ?
    ORDER BY v.valor_locacao ASC
"""

CONSULTA_AULAS_CONCLUIDAS = """
    SELECT COUNT(*) AS total
    FROM agendamentos
    WHERE instrutor_id = ? AND status = 'concluido'
"""


@instrutores_bp.route("/instrutor/<int:instrutor_id>")
def perfil(instrutor_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    conexao = get_connection()
    instrutor = conexao.execute(CONSULTA_PERFIL, (instrutor_id,)).fetchone()

    if instrutor is None:
        conexao.close()
        abort(404)

    avaliacoes = conexao.execute(CONSULTA_AVALIACOES, (instrutor_id,)).fetchall()
    veiculos = conexao.execute(CONSULTA_VEICULOS, (instrutor_id,)).fetchall()
    aulas_concluidas = conexao.execute(CONSULTA_AULAS_CONCLUIDAS, (instrutor_id,)).fetchone()["total"]
    conexao.close()

    return render_template(
        "perfil_instrutor.html",
        instrutor=instrutor,
        avaliacoes=avaliacoes,
        veiculos=veiculos,
        aulas_concluidas=aulas_concluidas,
    )
