from flask import Blueprint, redirect, render_template, request, session, url_for

from app.constantes import CATEGORIAS_CNH, CIDADES_ES
from database.db import get_connection

busca_bp = Blueprint("busca", __name__)

SELECT_BASE = """
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
"""

ORDENACOES = {
    "avaliacao": "(media_estrelas IS NULL), media_estrelas DESC, total_avaliacoes DESC",
    "menor_preco": "i.valor_aula ASC",
    "maior_preco": "i.valor_aula DESC",
}


def preferencias_salvas(usuario_id):
    conexao = get_connection()
    preferencias = conexao.execute(
        """
        SELECT prefere_instrutoras_mulheres,
               prefere_experiencia_neurodivergencia,
               prefere_experiencia_pcd
        FROM preferencias_candidato
        WHERE usuario_id = ?
        """,
        (usuario_id,),
    ).fetchone()
    acessibilidade = conexao.execute(
        "SELECT canal_comunicacao FROM perfis_acessibilidade WHERE usuario_id = ?",
        (usuario_id,),
    ).fetchone()
    conexao.close()

    if preferencias is None:
        return {}

    return {
        "somente_mulheres": bool(preferencias["prefere_instrutoras_mulheres"]),
        "neurodivergentes": bool(preferencias["prefere_experiencia_neurodivergencia"]),
        "pcd": bool(preferencias["prefere_experiencia_pcd"]),
        "libras": bool(acessibilidade and acessibilidade["canal_comunicacao"] == "libras"),
    }


def ler_filtros_do_formulario():
    return {
        "cidade": request.args.get("cidade", ""),
        "categoria": request.args.get("categoria", ""),
        "preco_maximo": request.args.get("preco_maximo", ""),
        "nota_minima": request.args.get("nota_minima", ""),
        "ordenar": request.args.get("ordenar", "avaliacao"),
        "somente_mulheres": "somente_mulheres" in request.args,
        "libras": "libras" in request.args,
        "neurodivergentes": "neurodivergentes" in request.args,
        "pcd": "pcd" in request.args,
        "veiculo_adaptado": "veiculo_adaptado" in request.args,
    }


def montar_consulta(filtros):
    condicoes = ["i.verificado = 1"]
    parametros = []

    if filtros["cidade"]:
        condicoes.append("u.cidade = ?")
        parametros.append(filtros["cidade"])

    if filtros["categoria"]:
        condicoes.append("i.categorias_cnh LIKE ?")
        parametros.append(f"%{filtros['categoria']}%")

    if filtros["preco_maximo"]:
        condicoes.append("i.valor_aula <= ?")
        parametros.append(float(filtros["preco_maximo"]))

    for chave, coluna in (
        ("somente_mulheres", "i.somente_mulheres"),
        ("libras", "i.atende_libras"),
        ("neurodivergentes", "i.atende_neurodivergentes"),
        ("pcd", "i.atende_pcd"),
        ("veiculo_adaptado", "i.veiculo_adaptado_disponivel"),
    ):
        if filtros[chave]:
            condicoes.append(f"{coluna} = 1")

    sql = SELECT_BASE + " WHERE " + " AND ".join(condicoes) + " GROUP BY i.id"

    if filtros["nota_minima"]:
        sql += " HAVING AVG(a.nota) >= ?"
        parametros.append(float(filtros["nota_minima"]))

    sql += " ORDER BY " + ORDENACOES.get(filtros["ordenar"], ORDENACOES["avaliacao"])

    return sql, parametros


@busca_bp.route("/busca")
def buscar():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    if request.args:
        filtros = ler_filtros_do_formulario()
    else:
        filtros = ler_filtros_do_formulario()
        filtros.update(preferencias_salvas(session["usuario_id"]))

    sql, parametros = montar_consulta(filtros)

    conexao = get_connection()
    instrutores = conexao.execute(sql, parametros).fetchall()
    conexao.close()

    return render_template(
        "busca.html",
        instrutores=instrutores,
        filtros=filtros,
        cidades=CIDADES_ES,
        categorias=CATEGORIAS_CNH,
    )
