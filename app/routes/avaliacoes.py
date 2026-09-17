import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from database.db import get_connection

avaliacoes_bp = Blueprint("avaliacoes", __name__)

CONSULTA_AULA = """
    SELECT ag.id,
           ag.status,
           ag.instrutor_id,
           ag.candidato_id,
           strftime('%d/%m/%Y', ag.data) AS data_formatada,
           ag.horario,
           u.nome AS nome_instrutor,
           u.foto_url,
           av.id  AS avaliacao_id
    FROM agendamentos ag
    JOIN instrutores i ON i.id = ag.instrutor_id
    JOIN usuarios u ON u.id = i.usuario_id
    LEFT JOIN avaliacoes av ON av.agendamento_id = ag.id
    WHERE ag.id = ?
"""


@avaliacoes_bp.route("/agendamento/<int:agendamento_id>/avaliar", methods=["GET", "POST"])
def avaliar(agendamento_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    conexao = get_connection()
    aula = conexao.execute(CONSULTA_AULA, (agendamento_id,)).fetchone()

    if aula is None or aula["candidato_id"] != session["usuario_id"]:
        conexao.close()
        abort(404)

    if aula["status"] != "concluido":
        conexao.close()
        flash("Você só pode avaliar depois que a aula for concluída.", "erro")
        return redirect(url_for("main.home"))

    if aula["avaliacao_id"]:
        conexao.close()
        flash("Você já avaliou essa aula.", "erro")
        return redirect(url_for("main.home"))

    if request.method == "POST":
        nota = request.form.get("nota", "")
        comentario = request.form.get("comentario", "").strip()

        if nota not in ("1", "2", "3", "4", "5"):
            conexao.close()
            flash("Escolha uma nota de 1 a 5 estrelas.", "erro")
            return redirect(url_for("avaliacoes.avaliar", agendamento_id=agendamento_id))

        try:
            conexao.execute(
                """
                INSERT INTO avaliacoes (agendamento_id, candidato_id, instrutor_id, nota, comentario)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agendamento_id, session["usuario_id"], aula["instrutor_id"], int(nota), comentario or None),
            )
            conexao.commit()
        except sqlite3.IntegrityError:
            conexao.rollback()
            flash("Essa aula já foi avaliada.", "erro")
            return redirect(url_for("main.home"))
        finally:
            conexao.close()

        flash("Avaliação enviada. Obrigado por ajudar outros candidatos!", "sucesso")
        return redirect(url_for("instrutores.perfil", instrutor_id=aula["instrutor_id"]))

    conexao.close()
    return render_template("avaliar.html", aula=aula)
