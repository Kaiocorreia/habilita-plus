from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.agenda import concluir_aulas_passadas
from app.constantes import ATENDIMENTOS_INSTRUTOR, CATEGORIAS_CNH
from app.consultas import SELECT_INSTRUTORES, VEICULOS_DO_INSTRUTOR
from app.formularios import validar_perfil_profissional
from app.sessao import exige_login
from database.db import get_connection

instrutores_bp = Blueprint("instrutores", __name__)

CONSULTA_PERFIL = SELECT_INSTRUTORES + " WHERE i.id = ? GROUP BY i.id"

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


@instrutores_bp.route("/instrutor/<int:instrutor_id>")
@exige_login()
def perfil(instrutor_id):
    conexao = get_connection()
    concluir_aulas_passadas(conexao)
    instrutor = conexao.execute(CONSULTA_PERFIL, (instrutor_id,)).fetchone()

    if instrutor is None:
        conexao.close()
        abort(404)

    avaliacoes = conexao.execute(CONSULTA_AVALIACOES, (instrutor_id,)).fetchall()
    veiculos = conexao.execute(VEICULOS_DO_INSTRUTOR, (instrutor_id,)).fetchall()
    aulas_concluidas = conexao.execute(
        "SELECT COUNT(*) FROM agendamentos WHERE instrutor_id = ? AND status = 'concluido'",
        (instrutor_id,),
    ).fetchone()[0]
    eh_dono = conexao.execute(
        "SELECT 1 FROM instrutores WHERE id = ? AND usuario_id = ?", (instrutor_id, g.usuario["id"])
    ).fetchone() is not None
    conexao.close()

    # Distribuição das notas (quantas de 5, de 4...) para o resumo de avaliações.
    distribuicao = {nota: 0 for nota in range(5, 0, -1)}
    for avaliacao in avaliacoes:
        distribuicao[avaliacao["nota"]] += 1

    return render_template(
        "perfil_instrutor.html",
        instrutor=instrutor,
        avaliacoes=avaliacoes,
        veiculos=veiculos,
        aulas_concluidas=aulas_concluidas,
        distribuicao=distribuicao,
        eh_dono=eh_dono,
        pode_agendar=g.usuario["tipo"] == "candidato",
    )


@instrutores_bp.route("/meu-perfil")
@exige_login(tipo="instrutor")
def meu_perfil():
    conexao = get_connection()
    instrutor = conexao.execute(
        "SELECT id FROM instrutores WHERE usuario_id = ?", (g.usuario["id"],)
    ).fetchone()
    conexao.close()
    if instrutor is None:
        abort(404)
    return redirect(url_for("instrutores.perfil", instrutor_id=instrutor["id"]))


@instrutores_bp.route("/perfil/editar", methods=["GET", "POST"])
@exige_login(tipo="instrutor")
def editar_perfil():
    conexao = get_connection()
    instrutor = conexao.execute(
        "SELECT * FROM instrutores WHERE usuario_id = ?", (g.usuario["id"],)
    ).fetchone()
    if instrutor is None:
        conexao.close()
        abort(404)

    contexto = {"categorias": CATEGORIAS_CNH, "atendimentos": ATENDIMENTOS_INSTRUTOR,
                "instrutor_id": instrutor["id"]}

    if request.method == "POST":
        dados, erro = validar_perfil_profissional(request.form)
        if erro:
            conexao.close()
            flash(erro, "erro")
            return render_template("editar_perfil.html", dados=dados, **contexto), 400

        conexao.execute(
            """
            UPDATE instrutores
               SET valor_aula = ?, regiao_atuacao = ?, atende_libras = ?, somente_mulheres = ?,
                   atende_neurodivergentes = ?, atende_pcd = ?, veiculo_adaptado_disponivel = ?
             WHERE id = ?
            """,
            (dados["valor_aula"], dados["regiao_atuacao"] or None, int(dados["atende_libras"]),
             int(dados["somente_mulheres"]), int(dados["atende_neurodivergentes"]),
             int(dados["atende_pcd"]), int(dados["veiculo_adaptado_disponivel"]), instrutor["id"]),
        )
        # Categorias: apaga e regrava. Numa tabela de junção, é mais simples (e
        # igualmente correto) do que calcular quais entraram e quais saíram.
        conexao.execute("DELETE FROM instrutor_categorias WHERE instrutor_id = ?", (instrutor["id"],))
        conexao.executemany(
            "INSERT INTO instrutor_categorias (instrutor_id, categoria) VALUES (?, ?)",
            [(instrutor["id"], categoria) for categoria in dados["categorias"]],
        )
        conexao.commit()
        conexao.close()

        # Os agendamentos já feitos mantêm o preço antigo: o valor foi copiado para
        # cada aula no momento da marcação, de propósito.
        flash("Perfil atualizado. Aulas já marcadas mantêm o valor combinado.", "sucesso")
        return redirect(url_for("instrutores.perfil", instrutor_id=instrutor["id"]))

    categorias = [linha["categoria"] for linha in conexao.execute(
        "SELECT categoria FROM instrutor_categorias WHERE instrutor_id = ? ORDER BY categoria",
        (instrutor["id"],),
    )]
    conexao.close()

    dados = {coluna: bool(instrutor[coluna]) for coluna, _r, _d in ATENDIMENTOS_INSTRUTOR}
    dados.update(
        categorias=categorias,
        regiao_atuacao=instrutor["regiao_atuacao"] or "",
        valor_texto=f"{instrutor['valor_aula']:.2f}".replace(".", ","),
    )
    return render_template("editar_perfil.html", dados=dados, **contexto)
