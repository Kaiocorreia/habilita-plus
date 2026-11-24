import calendar
import sqlite3
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from app.agenda import (JANELA_AGENDAMENTO_DIAS, concluir_aulas_passadas, data_agendavel,
                        data_por_extenso, horario_ja_passou, hoje, ler_data)
from app.constantes import DIAS_SEMANA_PT, HORARIOS_DISPONIVEIS, MESES_PT
from app.consultas import SELECT_AULAS, VEICULOS_DO_INSTRUTOR
from app.sessao import exige_login
from database.db import get_connection

agendamentos_bp = Blueprint("agendamentos", __name__)

CONSULTA_INSTRUTOR = """
    SELECT i.id, u.nome, u.foto_url, i.valor_aula, i.regiao_atuacao, i.verificado, u.cidade
    FROM instrutores i
    JOIN usuarios u ON u.id = i.usuario_id
    WHERE i.id = ?
"""

ATIVAS = "('agendado', 'confirmado')"
INSTRUTOR_INDISPONIVEL = "Esse instrutor não está mais disponível."


def _horarios_do_instrutor(conexao, instrutor_id, dia):
    return {linha["horario"] for linha in conexao.execute(
        f"SELECT horario FROM agendamentos WHERE instrutor_id = ? AND data = ? AND status IN {ATIVAS}",
        (instrutor_id, dia.isoformat()),
    )}


def _horarios_do_candidato(conexao, candidato_id, dia):
    return {linha["horario"] for linha in conexao.execute(
        f"SELECT horario FROM agendamentos WHERE candidato_id = ? AND data = ? AND status IN {ATIVAS}",
        (candidato_id, dia.isoformat()),
    )}


def validar_pedido(conexao, instrutor_id, data_texto, horario, veiculo_texto, candidato_id):
    """Confere um pedido de aula. Devolve (pedido, erro); exatamente um deles é None.

    Roda ao revisar e de novo ao confirmar: entre uma etapa e outra o horário
    pode ter sido ocupado, ou ter passado.
    """
    instrutor = conexao.execute(CONSULTA_INSTRUTOR, (instrutor_id,)).fetchone()
    if instrutor is None:
        return None, INSTRUTOR_INDISPONIVEL

    dia = ler_data(data_texto)
    if not data_agendavel(dia):
        return None, f"Escolha uma data entre hoje e os próximos {JANELA_AGENDAMENTO_DIAS} dias."

    if horario not in HORARIOS_DISPONIVEIS:
        return None, "Escolha um dos horários disponíveis."
    if horario_ja_passou(dia, horario):
        return None, "Esse horário já passou. Escolha outro."

    veiculo = None
    if veiculo_texto not in ("", None):
        try:
            veiculo_id = int(veiculo_texto)
        except (TypeError, ValueError):
            return None, "Veículo inválido."
        # O veículo precisa ser DESTE instrutor; um id de outro carro no formulário
        # não pode ser aceito.
        veiculo = conexao.execute(
            """
            SELECT v.* FROM veiculos v
            JOIN instrutor_veiculos iv ON iv.veiculo_id = v.id
            WHERE iv.instrutor_id = ? AND v.id = ?
            """,
            (instrutor_id, veiculo_id),
        ).fetchone()
        if veiculo is None:
            return None, "Esse veículo não está disponível com este instrutor."

    if horario in _horarios_do_instrutor(conexao, instrutor_id, dia):
        return None, "Esse horário acabou de ser reservado por outra pessoa. Escolha outro."
    if horario in _horarios_do_candidato(conexao, candidato_id, dia):
        return None, "Você já tem uma aula marcada nesse mesmo horário."

    return {"instrutor": instrutor, "dia": dia, "horario": horario, "veiculo": veiculo}, None


def montar_calendario(ano, mes):
    semanas = calendar.Calendar(firstweekday=6).monthdatescalendar(ano, mes)
    return [[dia if dia.month == mes else None for dia in semana] for semana in semanas]


@agendamentos_bp.route("/instrutor/<int:instrutor_id>/agendar")
@exige_login(tipo="candidato")
def escolher(instrutor_id):
    conexao = get_connection()
    instrutor = conexao.execute(CONSULTA_INSTRUTOR, (instrutor_id,)).fetchone()
    if instrutor is None:
        conexao.close()
        abort(404)

    hoje_ = hoje()
    limite = hoje_ + timedelta(days=JANELA_AGENDAMENTO_DIAS)

    dia_escolhido = ler_data(request.args.get("data"))
    if not data_agendavel(dia_escolhido):
        dia_escolhido = None

    # Mês exibido: o da URL, se válido e dentro da janela; senão o do dia escolhido
    # ou o atual. Assim o calendário nunca abre num mês sem dias marcáveis.
    referencia = dia_escolhido or hoje_
    try:
        ano, mes = (int(parte) for parte in request.args.get("mes", "").split("-"))
        if not date(ano, mes, 1) <= limite or date(ano, mes, calendar.monthrange(ano, mes)[1]) < hoje_:
            raise ValueError
    except (ValueError, TypeError):
        ano, mes = referencia.year, referencia.month

    horarios = []
    if dia_escolhido:
        do_instrutor = _horarios_do_instrutor(conexao, instrutor_id, dia_escolhido)
        do_candidato = _horarios_do_candidato(conexao, g.usuario["id"], dia_escolhido)
        for horario in HORARIOS_DISPONIVEIS:
            if horario_ja_passou(dia_escolhido, horario):
                motivo = "Horário já passou"
            elif horario in do_instrutor:
                motivo = "Reservado"
            elif horario in do_candidato:
                motivo = "Você já tem aula neste horário"
            else:
                motivo = None
            horarios.append({"hora": horario, "indisponivel": motivo})

    veiculos = conexao.execute(VEICULOS_DO_INSTRUTOR, (instrutor_id,)).fetchall()
    conexao.close()

    anterior = date(ano, mes, 1) - timedelta(days=1)
    seguinte = date(ano, mes, calendar.monthrange(ano, mes)[1]) + timedelta(days=1)

    return render_template(
        "agendar.html",
        instrutor=instrutor,
        veiculos=veiculos,
        semanas=montar_calendario(ano, mes),
        nome_mes=MESES_PT[mes - 1],
        ano=ano,
        mes=f"{ano}-{mes:02d}",
        mes_anterior=f"{anterior.year}-{anterior.month:02d}" if anterior >= hoje_.replace(day=1) else None,
        mes_seguinte=f"{seguinte.year}-{seguinte.month:02d}" if seguinte <= limite else None,
        dias_semana=DIAS_SEMANA_PT,
        hoje=hoje_,
        limite=limite,
        data_escolhida=dia_escolhido.isoformat() if dia_escolhido else "",
        data_extenso=data_por_extenso(dia_escolhido) if dia_escolhido else "",
        horarios=horarios,
        horarios_livres=sum(1 for h in horarios if not h["indisponivel"]),
        horario_marcado=request.args.get("horario", ""),
    )


@agendamentos_bp.route("/instrutor/<int:instrutor_id>/agendar", methods=["POST"])
@exige_login(tipo="candidato")
def revisar(instrutor_id):
    data_texto = request.form.get("data", "")
    horario = request.form.get("horario", "")
    veiculo_texto = request.form.get("veiculo_id", "")

    conexao = get_connection()
    pedido, erro = validar_pedido(conexao, instrutor_id, data_texto, horario, veiculo_texto, g.usuario["id"])
    conexao.close()

    if erro:
        flash(erro, "erro")
        if erro == INSTRUTOR_INDISPONIVEL:
            return redirect(url_for("busca.buscar"))
        return redirect(url_for("agendamentos.escolher", instrutor_id=instrutor_id,
                                data=data_texto if ler_data(data_texto) else None))

    session["agendamento"] = {
        "instrutor_id": instrutor_id,
        "data": pedido["dia"].isoformat(),
        "horario": horario,
        "veiculo_id": pedido["veiculo"]["id"] if pedido["veiculo"] else "",
    }
    return redirect(url_for("agendamentos.confirmar"))


@agendamentos_bp.route("/agendamento/confirmar", methods=["GET", "POST"])
@exige_login(tipo="candidato")
def confirmar():
    pendente = session.get("agendamento")
    if not pendente:
        return redirect(url_for("main.home"))

    conexao = get_connection()
    pedido, erro = validar_pedido(
        conexao, pendente["instrutor_id"], pendente["data"], pendente["horario"],
        pendente["veiculo_id"], g.usuario["id"],
    )

    if erro:
        conexao.close()
        session.pop("agendamento", None)
        flash(erro, "erro")
        if erro == INSTRUTOR_INDISPONIVEL:
            return redirect(url_for("busca.buscar"))
        return redirect(url_for("agendamentos.escolher", instrutor_id=pendente["instrutor_id"],
                                data=pendente["data"]))

    instrutor, veiculo = pedido["instrutor"], pedido["veiculo"]
    valor_locacao = veiculo["valor_locacao"] if veiculo else 0.0

    if request.method == "POST":
        try:
            # Os valores são COPIADOS para o agendamento: se o instrutor mudar o
            # preço amanhã, esta aula continua pelo valor combinado hoje.
            cursor = conexao.execute(
                """
                INSERT INTO agendamentos
                    (candidato_id, instrutor_id, veiculo_id, data, horario, status, valor, valor_locacao)
                VALUES (?, ?, ?, ?, ?, 'agendado', ?, ?)
                """,
                (g.usuario["id"], instrutor["id"], veiculo["id"] if veiculo else None,
                 pedido["dia"].isoformat(), pedido["horario"], instrutor["valor_aula"], valor_locacao),
            )
            conexao.commit()
        except sqlite3.IntegrityError:
            # Rede final contra a condição de corrida: o índice único parcial
            # recusa uma segunda aula ativa no mesmo instrutor, data e horário.
            conexao.rollback()
            conexao.close()
            session.pop("agendamento", None)
            flash("Esse horário acabou de ser reservado por outra pessoa. Escolha outro.", "erro")
            return redirect(url_for("agendamentos.escolher", instrutor_id=instrutor["id"],
                                    data=pedido["dia"].isoformat()))

        conexao.close()
        session.pop("agendamento", None)
        return redirect(url_for("agendamentos.sucesso", agendamento_id=cursor.lastrowid))

    conexao.close()
    return render_template(
        "agendamento_confirmar.html",
        instrutor=instrutor,
        veiculo=veiculo,
        data=pedido["dia"].isoformat(),
        data_extenso=data_por_extenso(pedido["dia"]),
        horario=pedido["horario"],
        valor_locacao=valor_locacao,
        total=instrutor["valor_aula"] + valor_locacao,
    )


@agendamentos_bp.route("/minhas-aulas")
@exige_login()
def minhas_aulas():
    conexao = get_connection()
    concluir_aulas_passadas(conexao)

    if g.usuario["tipo"] == "candidato":
        filtro = "ag.candidato_id = ?"
    else:
        filtro = "i.usuario_id = ?"

    aulas = conexao.execute(
        SELECT_AULAS + f" WHERE {filtro} ORDER BY ag.data DESC, ag.horario DESC",
        (g.usuario["id"],),
    ).fetchall()
    conexao.close()

    # Depois de concluir_aulas_passadas, toda aula ainda ativa está no futuro.
    proximas = sorted(
        (aula for aula in aulas if aula["status"] in ("agendado", "confirmado")),
        key=lambda aula: (aula["data"], aula["horario"]),
    )
    historico = [aula for aula in aulas if aula["status"] not in ("agendado", "confirmado")]

    return render_template("minhas_aulas.html", proximas=proximas, historico=historico,
                           visao=g.usuario["tipo"])


def _aula_do_usuario(conexao, agendamento_id):
    """Busca a aula se o usuário logado for o candidato ou o instrutor dela."""
    aula = conexao.execute(
        """
        SELECT ag.id, ag.status, ag.data, ag.horario, ag.candidato_id, i.usuario_id AS instrutor_usuario_id
        FROM agendamentos ag JOIN instrutores i ON i.id = ag.instrutor_id
        WHERE ag.id = ?
        """,
        (agendamento_id,),
    ).fetchone()
    # 404 (e não 403) para quem não participa da aula: não confirma nem que ela existe.
    if aula is None or g.usuario["id"] not in (aula["candidato_id"], aula["instrutor_usuario_id"]):
        conexao.close()
        abort(404)
    return aula


@agendamentos_bp.route("/agendamento/<int:agendamento_id>/cancelar", methods=["POST"])
@exige_login()
def cancelar(agendamento_id):
    conexao = get_connection()
    aula = _aula_do_usuario(conexao, agendamento_id)

    if aula["status"] not in ("agendado", "confirmado"):
        conexao.close()
        flash("Essa aula não pode mais ser cancelada.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    if horario_ja_passou(date.fromisoformat(aula["data"]), aula["horario"]):
        conexao.close()
        flash("Essa aula já começou e não pode mais ser cancelada.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    conexao.execute("UPDATE agendamentos SET status = 'cancelado' WHERE id = ?", (agendamento_id,))
    conexao.commit()
    conexao.close()

    flash("Aula cancelada. O horário voltou a ficar disponível.", "sucesso")
    return redirect(url_for("agendamentos.minhas_aulas"))


@agendamentos_bp.route("/agendamento/<int:agendamento_id>/aceitar", methods=["POST"])
@exige_login(tipo="instrutor")
def aceitar(agendamento_id):
    """O instrutor confirma a aula. Antes, o status 'confirmado' existia no banco
    mas nada no sistema o atribuía."""
    conexao = get_connection()
    aula = _aula_do_usuario(conexao, agendamento_id)

    if aula["instrutor_usuario_id"] != g.usuario["id"] or aula["status"] != "agendado":
        conexao.close()
        flash("Essa aula não está aguardando confirmação.", "erro")
        return redirect(url_for("agendamentos.minhas_aulas"))

    conexao.execute("UPDATE agendamentos SET status = 'confirmado' WHERE id = ?", (agendamento_id,))
    conexao.commit()
    conexao.close()

    flash("Aula confirmada. O candidato já vê a confirmação.", "sucesso")
    if request.form.get("voltar") == "home":
        return redirect(url_for("main.home"))
    return redirect(url_for("agendamentos.minhas_aulas"))


@agendamentos_bp.route("/agendamento/<int:agendamento_id>/sucesso")
@exige_login(tipo="candidato")
def sucesso(agendamento_id):
    conexao = get_connection()
    aula = conexao.execute(
        SELECT_AULAS + " WHERE ag.id = ? AND ag.candidato_id = ?",
        (agendamento_id, g.usuario["id"]),
    ).fetchone()
    conexao.close()

    if aula is None:
        abort(404)

    return render_template(
        "agendamento_sucesso.html",
        aula=aula,
        data_extenso=data_por_extenso(date.fromisoformat(aula["data"])),
        total=aula["valor"] + aula["valor_locacao"],
    )
