import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.agenda import concluir_aulas_passadas
from app.consultas import SELECT_AULAS
from app.sessao import exige_login
from database.db import get_connection

avaliacoes_bp = Blueprint("avaliacoes", __name__)

COMENTARIO_MAXIMO = 1000


@avaliacoes_bp.route("/agendamento/<int:agendamento_id>/avaliar", methods=["GET", "POST"])
@exige_login(tipo="candidato")
def avaliar(agendamento_id):
    conexao = get_connection()
    concluir_aulas_passadas(conexao)
    # Filtrar pelo candidato logado faz uma aula de outra pessoa simplesmente não
    # ser encontrada (404), sem revelar que ela existe.
    aula = conexao.execute(
        SELECT_AULAS + " WHERE ag.id = ? AND ag.candidato_id = ?", (agendamento_id, g.usuario["id"])
    ).fetchone()

    if aula is None:
        conexao.close()
        abort(404)

    # Três camadas contra avaliação indevida: esta checagem de status, a de
    # avaliação existente abaixo e o UNIQUE de agendamento_id no banco.
    if aula["status"] != "concluido":
        conexao.close()
        flash("Você poderá avaliar depois que a aula acontecer.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    if aula["avaliacao_id"]:
        conexao.close()
        flash("Você já avaliou essa aula.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    comentario = ""
    if request.method == "POST":
        nota = request.form.get("nota", "")
        comentario = request.form.get("comentario", "").strip()

        erro = None
        if nota not in ("1", "2", "3", "4", "5"):
            erro = "Escolha uma nota de 1 a 5 estrelas."
        elif len(comentario) > COMENTARIO_MAXIMO:
            erro = f"O comentário pode ter até {COMENTARIO_MAXIMO} caracteres."

        if erro:
            conexao.close()
            flash(erro, "erro")
            return render_template("avaliar.html", aula=aula, comentario=comentario,
                                   limite=COMENTARIO_MAXIMO), 400

        try:
            conexao.execute(
                """
                INSERT INTO avaliacoes (agendamento_id, candidato_id, instrutor_id, nota, comentario)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agendamento_id, g.usuario["id"], aula["instrutor_id"], int(nota), comentario or None),
            )
            conexao.commit()
        except sqlite3.IntegrityError:
            conexao.rollback()
            flash("Essa aula já foi avaliada.", "erro")
            return redirect(url_for("agendamentos.minhas_aulas"))
        finally:
            conexao.close()

        flash("Avaliação publicada. Obrigado por ajudar outros candidatos!", "sucesso")
        return redirect(url_for("instrutores.perfil", instrutor_id=aula["instrutor_id"]))

    conexao.close()
    return render_template("avaliar.html", aula=aula, comentario=comentario, limite=COMENTARIO_MAXIMO)
