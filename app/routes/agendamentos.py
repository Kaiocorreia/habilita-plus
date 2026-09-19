import calendar
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from app.constantes import DIAS_SEMANA_PT, HORARIOS_DISPONIVEIS, MESES_PT
from database.db import get_connection

agendamentos_bp = Blueprint("agendamentos", __name__)

CONSULTA_INSTRUTOR = """
    SELECT i.id, u.nome, u.foto_url, i.valor_aula, i.regiao_atuacao, i.verificado
    FROM instrutores i
    JOIN usuarios u ON u.id = i.usuario_id
    WHERE i.id = ?
"""

CONSULTA_VEICULOS = """
    SELECT v.id, v.marca, v.modelo, v.categoria_cnh, v.transmissao, v.adaptado,
           v.valor_locacao, v.imagem
    FROM veiculos v
    JOIN instrutor_veiculos iv ON iv.veiculo_id = v.id
    WHERE iv.instrutor_id = ?
    ORDER BY v.valor_locacao ASC
"""

CONSULTA_HORARIOS_OCUPADOS = """
    SELECT horario
    FROM agendamentos
    WHERE instrutor_id = ?
      AND data = ?
      AND status IN ('agendado', 'confirmado')
"""


def montar_calendario(ano, mes):
    semanas = calendar.Calendar(firstweekday=6).monthdatescalendar(ano, mes)
    return [[dia if dia.month == mes else None for dia in semana] for semana in semanas]


def mes_anterior(ano, mes):
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def mes_seguinte(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def formatar_data_extenso(data_iso):
    dia = date.fromisoformat(data_iso)
    return f"{dia.day} de {MESES_PT[dia.month - 1]} de {dia.year}"


@agendamentos_bp.route("/instrutor/<int:instrutor_id>/agendar")
def escolher(instrutor_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    if session.get("usuario_tipo") != "candidato":
        flash("Apenas candidatos podem agendar aulas.", "erro")
        return redirect(url_for("instrutores.perfil", instrutor_id=instrutor_id))

    conexao = get_connection()
    instrutor = conexao.execute(CONSULTA_INSTRUTOR, (instrutor_id,)).fetchone()

    if instrutor is None:
        conexao.close()
        abort(404)

    hoje = date.today()
    try:
        ano, mes = (int(parte) for parte in request.args.get("mes", "").split("-"))
        calendar.monthrange(ano, mes)
    except (ValueError, TypeError, calendar.IllegalMonthError):
        ano, mes = hoje.year, hoje.month

    data_escolhida = request.args.get("data", "")
    horarios_ocupados = []
    if data_escolhida:
        horarios_ocupados = [
            linha["horario"]
            for linha in conexao.execute(CONSULTA_HORARIOS_OCUPADOS, (instrutor_id, data_escolhida))
        ]

    veiculos = conexao.execute(CONSULTA_VEICULOS, (instrutor_id,)).fetchall()
    conexao.close()

    return render_template(
        "agendar.html",
        instrutor=instrutor,
        veiculos=veiculos,
        semanas=montar_calendario(ano, mes),
        nome_mes=MESES_PT[mes - 1],
        ano=ano,
        mes=f"{ano}-{mes:02d}",
        mes_anterior="%d-%02d" % mes_anterior(ano, mes),
        mes_seguinte="%d-%02d" % mes_seguinte(ano, mes),
        pode_voltar=(ano, mes) > (hoje.year, hoje.month),
        dias_semana=DIAS_SEMANA_PT,
        hoje=hoje,
        data_escolhida=data_escolhida,
        horarios=HORARIOS_DISPONIVEIS,
        horarios_ocupados=horarios_ocupados,
    )


@agendamentos_bp.route("/instrutor/<int:instrutor_id>/agendar", methods=["POST"])
def revisar(instrutor_id):
    if session.get("usuario_tipo") != "candidato":
        return redirect(url_for("auth.login"))

    data_escolhida = request.form.get("data", "")
    horario = request.form.get("horario", "")
    veiculo_id = request.form.get("veiculo_id", "")

    if not data_escolhida or not horario:
        flash("Escolha a data e o horário da aula.", "erro")
        return redirect(url_for("agendamentos.escolher", instrutor_id=instrutor_id, data=data_escolhida))

    if date.fromisoformat(data_escolhida) < date.today():
        flash("Não é possível agendar uma aula em data passada.", "erro")
        return redirect(url_for("agendamentos.escolher", instrutor_id=instrutor_id))

    session["agendamento"] = {
        "instrutor_id": instrutor_id,
        "data": data_escolhida,
        "horario": horario,
        "veiculo_id": int(veiculo_id) if veiculo_id else None,
    }
    return redirect(url_for("agendamentos.confirmar"))


@agendamentos_bp.route("/agendamento/confirmar", methods=["GET", "POST"])
def confirmar():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    pendente = session.get("agendamento")
    if not pendente:
        return redirect(url_for("main.home"))

    conexao = get_connection()
    instrutor = conexao.execute(CONSULTA_INSTRUTOR, (pendente["instrutor_id"],)).fetchone()

    veiculo = None
    if pendente["veiculo_id"]:
        veiculo = conexao.execute(
            "SELECT * FROM veiculos WHERE id = ?", (pendente["veiculo_id"],)
        ).fetchone()

    valor_locacao = veiculo["valor_locacao"] if veiculo else 0.0

    if request.method == "POST":
        ocupado = conexao.execute(
            CONSULTA_HORARIOS_OCUPADOS + " AND horario = ?",
            (pendente["instrutor_id"], pendente["data"], pendente["horario"]),
        ).fetchone()

        if ocupado:
            conexao.close()
            flash("Esse horário acabou de ser reservado por outra pessoa. Escolha outro.", "erro")
            return redirect(url_for("agendamentos.escolher",
                                    instrutor_id=pendente["instrutor_id"], data=pendente["data"]))

        cursor = conexao.execute(
            """
            INSERT INTO agendamentos
                (candidato_id, instrutor_id, veiculo_id, data, horario, status, valor, valor_locacao)
            VALUES (?, ?, ?, ?, ?, 'agendado', ?, ?)
            """,
            (
                session["usuario_id"], pendente["instrutor_id"], pendente["veiculo_id"],
                pendente["data"], pendente["horario"], instrutor["valor_aula"], valor_locacao,
            ),
        )
        conexao.commit()
        agendamento_id = cursor.lastrowid
        conexao.close()

        session.pop("agendamento", None)
        return redirect(url_for("agendamentos.sucesso", agendamento_id=agendamento_id))

    conexao.close()

    return render_template(
        "agendamento_confirmar.html",
        instrutor=instrutor,
        veiculo=veiculo,
        data_extenso=formatar_data_extenso(pendente["data"]),
        horario=pendente["horario"],
        valor_locacao=valor_locacao,
        total=instrutor["valor_aula"] + valor_locacao,
    )


CONSULTA_MINHAS_AULAS_COMPLETA = """
    SELECT ag.id,
           ag.data,
           ag.horario,
           ag.status,
           ag.valor,
           ag.valor_locacao,
           strftime('%d/%m/%Y', ag.data) AS data_formatada,
           ag.data >= date('now')        AS e_futura,
           u.nome  AS nome_instrutor,
           u.foto_url,
           i.id    AS instrutor_id,
           av.id   AS avaliacao_id,
           v.marca, v.modelo
    FROM agendamentos ag
    JOIN instrutores i ON i.id = ag.instrutor_id
    JOIN usuarios u ON u.id = i.usuario_id
    LEFT JOIN avaliacoes av ON av.agendamento_id = ag.id
    LEFT JOIN veiculos v ON v.id = ag.veiculo_id
    WHERE ag.candidato_id = ?
    ORDER BY ag.data DESC, ag.horario DESC
"""


@agendamentos_bp.route("/minhas-aulas")
def minhas_aulas():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    if session.get("usuario_tipo") != "candidato":
        return redirect(url_for("main.home"))

    conexao = get_connection()
    aulas = conexao.execute(CONSULTA_MINHAS_AULAS_COMPLETA, (session["usuario_id"],)).fetchall()
    conexao.close()

    proximas = [a for a in aulas if a["e_futura"] and a["status"] in ("agendado", "confirmado")]
    anteriores = [a for a in aulas if a not in proximas]

    return render_template("minhas_aulas.html", proximas=proximas, anteriores=anteriores)


@agendamentos_bp.route("/agendamento/<int:agendamento_id>/cancelar", methods=["POST"])
def cancelar(agendamento_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    conexao = get_connection()
    aula = conexao.execute(
        "SELECT candidato_id, status, data FROM agendamentos WHERE id = ?",
        (agendamento_id,),
    ).fetchone()

    if aula is None or aula["candidato_id"] != session["usuario_id"]:
        conexao.close()
        abort(404)

    if aula["status"] not in ("agendado", "confirmado"):
        conexao.close()
        flash("Essa aula não pode mais ser cancelada.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    if date.fromisoformat(aula["data"]) < date.today():
        conexao.close()
        flash("Não é possível cancelar uma aula que já aconteceu.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    conexao.execute(
        "UPDATE agendamentos SET status = 'cancelado' WHERE id = ?",
        (agendamento_id,),
    )
    conexao.commit()
    conexao.close()

    flash("Aula cancelada. O horário voltou a ficar disponível.", "sucesso")
    return redirect(url_for("agendamentos.minhas_aulas"))


@agendamentos_bp.route("/agendamento/<int:agendamento_id>/sucesso")
def sucesso(agendamento_id):
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    conexao = get_connection()
    agendamento = conexao.execute(
        """
        SELECT ag.data, ag.horario, ag.valor, ag.valor_locacao,
               u.nome AS nome_instrutor,
               v.marca, v.modelo
        FROM agendamentos ag
        JOIN instrutores i ON i.id = ag.instrutor_id
        JOIN usuarios u ON u.id = i.usuario_id
        LEFT JOIN veiculos v ON v.id = ag.veiculo_id
        WHERE ag.id = ? AND ag.candidato_id = ?
        """,
        (agendamento_id, session["usuario_id"]),
    ).fetchone()
    conexao.close()

    if agendamento is None:
        abort(404)

    return render_template(
        "agendamento_sucesso.html",
        agendamento=agendamento,
        data_extenso=formatar_data_extenso(agendamento["data"]),
        total=agendamento["valor"] + agendamento["valor_locacao"],
    )
