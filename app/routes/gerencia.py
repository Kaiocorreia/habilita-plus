"""Área da gerência: aprovação de instrutores, moderação, veículos e configurações.

Só contas do tipo 'gerente' entram aqui. Não existe cadastro de gerente pelo
site; a conta é criada no servidor com database/criar_gerente.py.
"""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.agenda import hoje
from app.configuracoes import (AVISO_MAXIMO, HORARIOS_POSSIVEIS, JANELA_MAXIMA, JANELA_MINIMA,
                               configuracoes, salvar)
from app.constantes import CATEGORIAS_CNH
from app.sessao import destino_seguro, exige_login
from database.db import get_connection

gerencia_bp = Blueprint("gerencia", __name__, url_prefix="/gerencia")

IMAGENS_VEICULOS = {
    "img/veiculos/hatch.svg": "Hatch",
    "img/veiculos/sedan.svg": "Sedã",
    "img/veiculos/moto.svg": "Moto",
    "img/veiculos/adaptado.svg": "Adaptado",
}

# Cada ação sobre um instrutor: (coluna, novo valor, mensagem, rótulo no registro).
ACOES_INSTRUTOR = {
    "aprovar": ("verificado", 1, "Perfil aprovado. O selo de verificado já aparece no site.", "Aprovou"),
    "revogar": ("verificado", 0, "Verificação revogada. O perfil voltou para “Em análise”.", "Revogou a verificação de"),
    "suspender": ("ativo", 0, "Perfil suspenso. Ele saiu das buscas e não recebe novos agendamentos.", "Suspendeu"),
    "reativar": ("ativo", 1, "Perfil reativado. Ele voltou a aparecer nas buscas.", "Reativou"),
}

FILTROS_INSTRUTOR = {
    "pendentes": ("Em análise", "i.verificado = 0 AND i.ativo = 1"),
    "verificados": ("Verificados", "i.verificado = 1 AND i.ativo = 1"),
    "suspensos": ("Suspensos", "i.ativo = 0"),
    "todos": ("Todos", "1 = 1"),
}

CONSULTA_INSTRUTORES = """
    SELECT i.id, i.verificado, i.ativo, i.valor_aula, i.regiao_atuacao,
           i.atende_libras, i.atende_pcd, i.atende_neurodivergentes,
           i.veiculo_adaptado_disponivel, i.somente_mulheres,
           u.nome, u.email, u.cidade, u.telefone, u.foto_url,
           strftime('%d/%m/%Y', u.data_cadastro) AS cadastro,
           (SELECT GROUP_CONCAT(categoria, ', ') FROM
               (SELECT categoria FROM instrutor_categorias WHERE instrutor_id = i.id ORDER BY categoria))
               AS categorias_cnh,
           (SELECT ROUND(AVG(nota), 1) FROM avaliacoes WHERE instrutor_id = i.id AND oculta = 0) AS media,
           (SELECT COUNT(*) FROM avaliacoes WHERE instrutor_id = i.id AND oculta = 0) AS total_avaliacoes,
           (SELECT COUNT(*) FROM agendamentos WHERE instrutor_id = i.id
               AND status IN ('agendado', 'confirmado')) AS aulas_futuras
    FROM instrutores i
    JOIN usuarios u ON u.id = i.usuario_id
"""


def registrar(conexao, acao, alvo, detalhe=None):
    """Grava a ação no registro da gerência. Não faz commit: entra na mesma
    transação da mudança, então ou as duas ficam gravadas ou nenhuma."""
    conexao.execute(
        "INSERT INTO acoes_gerenciais (gerente_id, acao, alvo, detalhe) VALUES (?, ?, ?, ?)",
        (g.usuario["id"], acao, alvo, detalhe),
    )


def _ultimas_acoes(conexao, limite):
    return conexao.execute(
        """
        SELECT a.acao, a.alvo, a.detalhe, u.nome AS gerente,
               strftime('%d/%m/%Y %H:%M', a.data, '-3 hours') AS quando
        FROM acoes_gerenciais a JOIN usuarios u ON u.id = a.gerente_id
        ORDER BY a.id DESC LIMIT ?
        """,
        (limite,),
    ).fetchall()


# --- Painel ------------------------------------------------------------------

@gerencia_bp.route("")
@exige_login(tipo="gerente")
def painel():
    conexao = get_connection()
    numeros = conexao.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM instrutores WHERE verificado = 0 AND ativo = 1) AS pendentes,
          (SELECT COUNT(*) FROM instrutores WHERE ativo = 1)                    AS instrutores,
          (SELECT COUNT(*) FROM instrutores WHERE ativo = 0)                    AS suspensos,
          (SELECT COUNT(*) FROM usuarios WHERE tipo = 'candidato')              AS candidatos,
          (SELECT COUNT(*) FROM agendamentos WHERE status IN ('agendado', 'confirmado')
              AND data BETWEEN ? AND date(?, '+7 days'))                        AS aulas_semana,
          (SELECT COUNT(*) FROM avaliacoes WHERE oculta = 1)                    AS ocultas
        """,
        (hoje().isoformat(), hoje().isoformat()),
    ).fetchone()
    fila = conexao.execute(
        CONSULTA_INSTRUTORES + " WHERE i.verificado = 0 AND i.ativo = 1 ORDER BY u.data_cadastro LIMIT 5"
    ).fetchall()
    acoes = _ultimas_acoes(conexao, 8)
    conexao.close()
    return render_template("gerencia/painel.html", numeros=numeros, fila=fila, acoes=acoes,
                           config=configuracoes())


# --- Instrutores -------------------------------------------------------------

@gerencia_bp.route("/instrutores")
@exige_login(tipo="gerente")
def instrutores():
    filtro = request.args.get("filtro", "pendentes")
    if filtro not in FILTROS_INSTRUTOR:
        filtro = "pendentes"
    busca = " ".join(request.args.get("q", "").split())[:60]

    condicao, parametros = FILTROS_INSTRUTOR[filtro][1], []
    if busca:
        condicao += " AND (u.nome LIKE ? OR u.email LIKE ? OR u.cidade LIKE ?)"
        parametros = [f"%{busca}%"] * 3

    conexao = get_connection()
    lista = conexao.execute(
        CONSULTA_INSTRUTORES + f" WHERE {condicao} ORDER BY i.verificado, u.data_cadastro DESC", parametros
    ).fetchall()
    contagens = {
        chave: conexao.execute(f"SELECT COUNT(*) FROM instrutores i WHERE {cond}").fetchone()[0]
        for chave, (_rotulo, cond) in FILTROS_INSTRUTOR.items()
    }
    conexao.close()
    return render_template("gerencia/instrutores.html", lista=lista, filtro=filtro, busca=busca,
                           filtros=FILTROS_INSTRUTOR, contagens=contagens)


@gerencia_bp.route("/instrutores/<int:instrutor_id>/<acao>", methods=["POST"])
@exige_login(tipo="gerente")
def acao_instrutor(instrutor_id, acao):
    if acao not in ACOES_INSTRUTOR:
        abort(404)
    coluna, valor, mensagem, rotulo = ACOES_INSTRUTOR[acao]

    conexao = get_connection()
    instrutor = conexao.execute(
        "SELECT i.id, u.nome, i.verificado, i.ativo FROM instrutores i JOIN usuarios u ON u.id = i.usuario_id WHERE i.id = ?",
        (instrutor_id,),
    ).fetchone()
    if instrutor is None:
        conexao.close()
        abort(404)

    if instrutor[coluna] == valor:
        conexao.close()
        flash("Nada mudou: o perfil já estava nesse estado.", "erro")
    else:
        # A coluna vem do dicionário fixo acima, nunca do usuário.
        conexao.execute(f"UPDATE instrutores SET {coluna} = ? WHERE id = ?", (valor, instrutor_id))
        registrar(conexao, rotulo, instrutor["nome"])
        conexao.commit()

        if acao == "suspender":
            futuras = conexao.execute(
                "SELECT COUNT(*) FROM agendamentos WHERE instrutor_id = ? AND status IN ('agendado', 'confirmado')",
                (instrutor_id,),
            ).fetchone()[0]
            if futuras:
                mensagem += f" {futuras} aula(s) já marcada(s) continuam valendo."
        conexao.close()
        flash(mensagem, "sucesso")

    # "voltar" vem do formulário: só caminhos internos, para não virar redirecionamento aberto.
    voltar = request.form.get("voltar")
    return redirect(destino_seguro(voltar) if voltar else url_for("gerencia.instrutores"))


# --- Avaliações --------------------------------------------------------------

@gerencia_bp.route("/avaliacoes")
@exige_login(tipo="gerente")
def avaliacoes():
    filtro = request.args.get("filtro", "visiveis")
    filtro = filtro if filtro in ("visiveis", "ocultas") else "visiveis"

    conexao = get_connection()
    lista = conexao.execute(
        """
        SELECT av.id, av.nota, av.comentario, av.oculta,
               strftime('%d/%m/%Y', av.data) AS data_formatada,
               uc.nome AS candidato, ui.nome AS instrutor, i.id AS instrutor_id
        FROM avaliacoes av
        JOIN usuarios uc ON uc.id = av.candidato_id
        JOIN instrutores i ON i.id = av.instrutor_id
        JOIN usuarios ui ON ui.id = i.usuario_id
        WHERE av.oculta = ?
        ORDER BY av.data DESC
        """,
        (1 if filtro == "ocultas" else 0,),
    ).fetchall()
    contagens = {
        "visiveis": conexao.execute("SELECT COUNT(*) FROM avaliacoes WHERE oculta = 0").fetchone()[0],
        "ocultas": conexao.execute("SELECT COUNT(*) FROM avaliacoes WHERE oculta = 1").fetchone()[0],
    }
    conexao.close()
    return render_template("gerencia/avaliacoes.html", lista=lista, filtro=filtro, contagens=contagens)


@gerencia_bp.route("/avaliacoes/<int:avaliacao_id>/<acao>", methods=["POST"])
@exige_login(tipo="gerente")
def acao_avaliacao(avaliacao_id, acao):
    if acao not in ("ocultar", "restaurar"):
        abort(404)

    conexao = get_connection()
    avaliacao = conexao.execute(
        """SELECT av.id, av.nota, ui.nome AS instrutor FROM avaliacoes av
           JOIN instrutores i ON i.id = av.instrutor_id JOIN usuarios ui ON ui.id = i.usuario_id
           WHERE av.id = ?""",
        (avaliacao_id,),
    ).fetchone()
    if avaliacao is None:
        conexao.close()
        abort(404)

    # Ocultar, e não apagar: a decisão pode ser revista, e o histórico fica.
    conexao.execute("UPDATE avaliacoes SET oculta = ? WHERE id = ?",
                    (1 if acao == "ocultar" else 0, avaliacao_id))
    registrar(conexao, "Ocultou avaliação de" if acao == "ocultar" else "Restaurou avaliação de",
              avaliacao["instrutor"], f"Nota {avaliacao['nota']}")
    conexao.commit()
    conexao.close()

    flash("Avaliação ocultada. A média do instrutor já foi recalculada." if acao == "ocultar"
          else "Avaliação restaurada no perfil do instrutor.", "sucesso")
    return redirect(url_for("gerencia.avaliacoes", filtro="visiveis" if acao == "ocultar" else "ocultas"))


# --- Veículos ----------------------------------------------------------------

def _ler_veiculo(form, ids_validos):
    """Valida o formulário de veículo. Devolve (dados, erro)."""
    dados = {
        "marca": " ".join(form.get("marca", "").split())[:40],
        "modelo": " ".join(form.get("modelo", "").split())[:40],
        "categoria_cnh": form.get("categoria_cnh", ""),
        "transmissao": form.get("transmissao", ""),
        "adaptado": "adaptado" in form,
        "imagem": form.get("imagem", ""),
        "valor_texto": form.get("valor_locacao", "").strip(),
        "instrutores": [int(i) for i in form.getlist("instrutores") if i.isdigit() and int(i) in ids_validos],
    }
    if not dados["marca"] or not dados["modelo"]:
        return dados, "Informe a marca e o modelo."
    if dados["categoria_cnh"] not in CATEGORIAS_CNH:
        return dados, "Escolha a categoria de CNH do veículo."
    if dados["transmissao"] not in ("manual", "automatico"):
        return dados, "Escolha o tipo de câmbio."
    if dados["imagem"] not in IMAGENS_VEICULOS:
        return dados, "Escolha uma ilustração para o veículo."
    try:
        valor = float(dados["valor_texto"].replace("R$", "").replace(",", ".").strip())
    except ValueError:
        return dados, "Informe o valor da locação, por exemplo 35,00."
    if not 0 <= valor <= 1000:
        return dados, "A locação deve ficar entre R$ 0 e R$ 1.000."
    dados["valor_locacao"] = round(valor, 2)
    return dados, None


def _instrutores_para_vinculo(conexao):
    return conexao.execute(
        "SELECT i.id, u.nome, i.ativo FROM instrutores i JOIN usuarios u ON u.id = i.usuario_id ORDER BY u.nome"
    ).fetchall()


@gerencia_bp.route("/veiculos")
@exige_login(tipo="gerente")
def veiculos():
    conexao = get_connection()
    lista = conexao.execute(
        """
        SELECT v.*,
               (SELECT GROUP_CONCAT(u.nome, ', ') FROM instrutor_veiculos iv
                  JOIN instrutores i ON i.id = iv.instrutor_id JOIN usuarios u ON u.id = i.usuario_id
                  WHERE iv.veiculo_id = v.id) AS instrutores,
               (SELECT COUNT(*) FROM agendamentos WHERE veiculo_id = v.id) AS usos
        FROM veiculos v ORDER BY v.categoria_cnh, v.valor_locacao
        """
    ).fetchall()
    conexao.close()
    return render_template("gerencia/veiculos.html", lista=lista)


@gerencia_bp.route("/veiculos/novo", methods=["GET", "POST"])
@gerencia_bp.route("/veiculos/<int:veiculo_id>", methods=["GET", "POST"])
@exige_login(tipo="gerente")
def editar_veiculo(veiculo_id=None):
    conexao = get_connection()
    opcoes = _instrutores_para_vinculo(conexao)
    veiculo = None
    if veiculo_id is not None:
        veiculo = conexao.execute("SELECT * FROM veiculos WHERE id = ?", (veiculo_id,)).fetchone()
        if veiculo is None:
            conexao.close()
            abort(404)

    contexto = {"veiculo_id": veiculo_id, "opcoes": opcoes, "imagens": IMAGENS_VEICULOS,
                "categorias": CATEGORIAS_CNH}

    if request.method == "POST":
        dados, erro = _ler_veiculo(request.form, {o["id"] for o in opcoes})
        if erro:
            conexao.close()
            flash(erro, "erro")
            return render_template("gerencia/veiculo_form.html", dados=dados, **contexto), 400

        campos = (dados["marca"], dados["modelo"], dados["categoria_cnh"], dados["transmissao"],
                  int(dados["adaptado"]), dados["valor_locacao"], dados["imagem"])
        if veiculo is None:
            veiculo_id = conexao.execute(
                """INSERT INTO veiculos (marca, modelo, categoria_cnh, transmissao, adaptado, valor_locacao, imagem)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""", campos,
            ).lastrowid
            acao = "Cadastrou o veículo"
        else:
            conexao.execute(
                """UPDATE veiculos SET marca = ?, modelo = ?, categoria_cnh = ?, transmissao = ?,
                   adaptado = ?, valor_locacao = ?, imagem = ? WHERE id = ?""", campos + (veiculo_id,),
            )
            acao = "Editou o veículo"

        conexao.execute("DELETE FROM instrutor_veiculos WHERE veiculo_id = ?", (veiculo_id,))
        conexao.executemany("INSERT INTO instrutor_veiculos (instrutor_id, veiculo_id) VALUES (?, ?)",
                            [(i, veiculo_id) for i in dados["instrutores"]])
        registrar(conexao, acao, f"{dados['marca']} {dados['modelo']}",
                  f"{len(dados['instrutores'])} instrutor(es) · locação R$ {dados['valor_locacao']:.2f}")
        conexao.commit()
        conexao.close()

        # Aulas já marcadas guardam o valor da locação da época (cópia proposital).
        flash("Veículo salvo. Ele já aparece no perfil e no agendamento dos instrutores vinculados.", "sucesso")
        return redirect(url_for("gerencia.veiculos"))

    if veiculo is None:
        dados = {"instrutores": [], "imagem": "img/veiculos/hatch.svg", "transmissao": "manual",
                 "categoria_cnh": "B"}
    else:
        dados = dict(veiculo)
        dados["valor_texto"] = f"{veiculo['valor_locacao']:.2f}".replace(".", ",")
        dados["instrutores"] = [linha["instrutor_id"] for linha in conexao.execute(
            "SELECT instrutor_id FROM instrutor_veiculos WHERE veiculo_id = ?", (veiculo_id,))]
    conexao.close()
    return render_template("gerencia/veiculo_form.html", dados=dados, **contexto)


# --- Configurações -----------------------------------------------------------

@gerencia_bp.route("/configuracoes", methods=["GET", "POST"])
@exige_login(tipo="gerente")
def configuracoes_site():
    atuais = configuracoes()
    contexto = {"horarios_possiveis": HORARIOS_POSSIVEIS, "janela_minima": JANELA_MINIMA,
                "janela_maxima": JANELA_MAXIMA, "aviso_maximo": AVISO_MAXIMO}

    if request.method == "POST":
        horarios = [h for h in HORARIOS_POSSIVEIS if h in request.form.getlist("horarios")]
        aviso = " ".join(request.form.get("aviso_texto", "").split())
        aviso_ativo = "aviso_ativo" in request.form
        erro = None
        try:
            janela = int(request.form.get("janela_dias", ""))
        except ValueError:
            janela = None

        if not horarios:
            erro = "Mantenha pelo menos um horário de aula disponível."
        elif janela is None or not JANELA_MINIMA <= janela <= JANELA_MAXIMA:
            erro = f"A janela de agendamento deve ficar entre {JANELA_MINIMA} e {JANELA_MAXIMA} dias."
        elif len(aviso) > AVISO_MAXIMO:
            erro = f"O aviso pode ter até {AVISO_MAXIMO} caracteres."
        elif aviso_ativo and not aviso:
            erro = "Escreva o texto do aviso antes de ativá-lo."

        if erro:
            flash(erro, "erro")
            rascunho = {"horarios": horarios, "janela_dias": janela or atuais["janela_dias"],
                        "aviso_texto": aviso, "aviso_ativo": aviso_ativo}
            return render_template("gerencia/configuracoes.html", config=rascunho, **contexto), 400

        conexao = get_connection()
        salvar(conexao, {"horarios": ",".join(horarios), "janela_dias": str(janela),
                         "aviso_texto": aviso, "aviso_ativo": "1" if aviso_ativo else "0"})
        mudancas = []
        if horarios != atuais["horarios"]:
            mudancas.append(f"{len(horarios)} horários")
        if janela != atuais["janela_dias"]:
            mudancas.append(f"janela de {janela} dias")
        if (aviso, aviso_ativo) != (atuais["aviso_texto"], atuais["aviso_ativo"]):
            mudancas.append("aviso " + ("ativado" if aviso_ativo else "desativado"))
        if mudancas:
            registrar(conexao, "Alterou as configurações", "da plataforma", ", ".join(mudancas))
        conexao.commit()
        conexao.close()

        flash("Configurações salvas. Elas já valem em todo o site." if mudancas
              else "Nada mudou nas configurações.", "sucesso")
        return redirect(url_for("gerencia.configuracoes_site"))

    return render_template("gerencia/configuracoes.html", config=atuais, **contexto)


# --- Registro ----------------------------------------------------------------

@gerencia_bp.route("/registro")
@exige_login(tipo="gerente")
def registro():
    conexao = get_connection()
    acoes = _ultimas_acoes(conexao, 200)
    conexao.close()
    return render_template("gerencia/registro.html", acoes=acoes)
