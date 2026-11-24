from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from datetime import timedelta

from app.agenda import concluir_aulas_passadas, data_por_extenso, hoje, ler_data
from app.constantes import ATENDIMENTOS_INSTRUTOR, CATEGORIAS_CNH
from app.consultas import SELECT_INSTRUTORES, VEICULOS_DO_INSTRUTOR
from app.formularios import validar_perfil_profissional
from app.sessao import destino_seguro, exige_login
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
    WHERE av.instrutor_id = ? AND av.oculta = 0
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

    eh_dono = conexao.execute(
        "SELECT 1 FROM instrutores WHERE id = ? AND usuario_id = ?", (instrutor_id, g.usuario["id"])
    ).fetchone() is not None

    # Perfil suspenso pela gerência: para os candidatos, é como se não existisse.
    if not instrutor["ativo"] and not eh_dono and g.usuario["tipo"] != "gerente":
        conexao.close()
        abort(404)

    avaliacoes = conexao.execute(CONSULTA_AVALIACOES, (instrutor_id,)).fetchall()
    salvo = conexao.execute(
        "SELECT 1 FROM favoritos WHERE usuario_id = ? AND instrutor_id = ?", (g.usuario["id"], instrutor_id)
    ).fetchone() is not None
    veiculos = conexao.execute(VEICULOS_DO_INSTRUTOR, (instrutor_id,)).fetchall()
    aulas_concluidas = conexao.execute(
        "SELECT COUNT(*) FROM agendamentos WHERE instrutor_id = ? AND status = 'concluido'",
        (instrutor_id,),
    ).fetchone()[0]
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
        salvo=salvo,
        pode_agendar=g.usuario["tipo"] == "candidato" and bool(instrutor["ativo"]),
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


# --- Favoritos (candidato) ---------------------------------------------------

@instrutores_bp.route("/instrutor/<int:instrutor_id>/salvar", methods=["POST"])
@exige_login(tipo="candidato")
def alternar_favorito(instrutor_id):
    conexao = get_connection()
    if conexao.execute("SELECT 1 FROM instrutores WHERE id = ? AND ativo = 1", (instrutor_id,)).fetchone() is None:
        conexao.close()
        abort(404)

    apagou = conexao.execute(
        "DELETE FROM favoritos WHERE usuario_id = ? AND instrutor_id = ?", (g.usuario["id"], instrutor_id)
    ).rowcount
    if not apagou:
        conexao.execute("INSERT INTO favoritos (usuario_id, instrutor_id) VALUES (?, ?)", (g.usuario["id"], instrutor_id))
    conexao.commit()
    conexao.close()

    flash("Removido dos seus salvos." if apagou else "Instrutor salvo. Ele aparece no seu início.", "sucesso")
    voltar = request.form.get("voltar")
    return redirect(destino_seguro(voltar) if voltar else url_for("instrutores.perfil", instrutor_id=instrutor_id))


# --- Folgas (instrutor) ------------------------------------------------------

FOLGA_MAXIMA_DIAS = 365


def _meu_instrutor_id(conexao):
    linha = conexao.execute("SELECT id FROM instrutores WHERE usuario_id = ?", (g.usuario["id"],)).fetchone()
    if linha is None:
        conexao.close()
        abort(404)
    return linha["id"]


@instrutores_bp.route("/agenda/folgas", methods=["GET", "POST"])
@exige_login(tipo="instrutor")
def folgas():
    conexao = get_connection()
    instrutor_id = _meu_instrutor_id(conexao)

    if request.method == "POST":
        dia = ler_data(request.form.get("data"))
        if dia is None or not hoje() <= dia <= hoje() + timedelta(days=FOLGA_MAXIMA_DIAS):
            flash("Escolha uma data entre hoje e os próximos 12 meses.", "erro")
        else:
            conexao.execute("INSERT OR IGNORE INTO folgas (instrutor_id, data) VALUES (?, ?)",
                            (instrutor_id, dia.isoformat()))
            conexao.commit()
            marcadas = conexao.execute(
                "SELECT COUNT(*) FROM agendamentos WHERE instrutor_id = ? AND data = ? AND status IN ('agendado', 'confirmado')",
                (instrutor_id, dia.isoformat()),
            ).fetchone()[0]
            mensagem = f"Folga marcada em {data_por_extenso(dia)}. Ninguém consegue agendar nesse dia."
            if marcadas:
                mensagem += f" Atenção: {marcadas} aula(s) já marcada(s) nesse dia continuam valendo."
            flash(mensagem, "sucesso")
        conexao.close()
        return redirect(url_for("instrutores.folgas"))

    lista = conexao.execute(
        """
        SELECT f.data,
               (SELECT COUNT(*) FROM agendamentos ag WHERE ag.instrutor_id = f.instrutor_id AND ag.data = f.data
                  AND ag.status IN ('agendado', 'confirmado')) AS aulas
        FROM folgas f WHERE f.instrutor_id = ? AND f.data >= ? ORDER BY f.data
        """,
        (instrutor_id, hoje().isoformat()),
    ).fetchall()
    conexao.close()
    folgas_futuras = [{"data": linha["data"], "extenso": data_por_extenso(ler_data(linha["data"])), "aulas": linha["aulas"]}
                      for linha in lista]
    return render_template("folgas.html", folgas=folgas_futuras, hoje=hoje().isoformat(),
                           limite=(hoje() + timedelta(days=FOLGA_MAXIMA_DIAS)).isoformat())


@instrutores_bp.route("/agenda/folgas/<data>/remover", methods=["POST"])
@exige_login(tipo="instrutor")
def remover_folga(data):
    conexao = get_connection()
    instrutor_id = _meu_instrutor_id(conexao)
    conexao.execute("DELETE FROM folgas WHERE instrutor_id = ? AND data = ?", (instrutor_id, data))
    conexao.commit()
    conexao.close()
    flash("Folga removida. O dia voltou a aceitar agendamentos.", "sucesso")
    return redirect(url_for("instrutores.folgas"))
