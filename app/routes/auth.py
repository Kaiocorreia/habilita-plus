import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.constantes import (ATENDIMENTOS_INSTRUTOR, CANAIS_COMUNICACAO, CATEGORIAS_CNH,
                            CIDADES_ES, DDD_PADRAO, TIPOS_DEFICIENCIA)
from app.formularios import categorias_marcadas, validar_dados_pessoais, validar_perfil_profissional
from app.sessao import destino_seguro, iniciar_sessao
from database.db import get_connection

auth_bp = Blueprint("auth", __name__)

# Comparado quando o e-mail não existe, para o login demorar o mesmo tempo nos dois
# casos. Sem isso, medir o tempo de resposta revelaria quais e-mails têm conta.
HASH_DE_COMPARACAO = generate_password_hash("habilita-plus-sem-conta")


def _etapas(tipo):
    return 4 if tipo == "candidato" else 2


def _cadastro_em_andamento(*chaves_exigidas):
    """O cadastro em etapas, se o usuário chegou até aqui na ordem certa."""
    cadastro = session.get("cadastro")
    if not cadastro or any(chave not in cadastro for chave in chaves_exigidas):
        return None
    return cadastro


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    proximo = request.values.get("proximo", "")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        conexao = get_connection()
        usuario = conexao.execute(
            "SELECT id, nome, senha_hash, tipo FROM usuarios WHERE email = ?", (email,)
        ).fetchone()
        conexao.close()

        hash_salvo = usuario["senha_hash"] if usuario else HASH_DE_COMPARACAO
        senha_confere = check_password_hash(hash_salvo, senha)

        if usuario is None or not senha_confere:
            # A mesma mensagem nos dois casos, pelo mesmo motivo do hash acima.
            flash("E-mail ou senha incorretos.", "erro")
            return render_template("login.html", email=email, proximo=proximo), 401

        iniciar_sessao(usuario)
        return redirect(destino_seguro(proximo))

    if session.get("usuario_id"):
        return redirect(url_for("main.home"))
    return render_template("login.html", email="", proximo=proximo)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    # Sair só por POST (com token CSRF): um link ou imagem em outro site não
    # consegue derrubar a sessão de ninguém. Um GET antigo apenas volta ao início.
    if request.method == "POST":
        session.clear()
        flash("Você saiu da sua conta.", "sucesso")
        return redirect(url_for("auth.login"))
    return redirect(url_for("main.home"))


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro_tipo():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        if tipo not in ("candidato", "instrutor"):
            flash("Escolha uma das opções para continuar.", "erro")
            return render_template("cadastro_tipo.html"), 400

        session["cadastro"] = {"tipo": tipo}
        return redirect(url_for("auth.cadastro_dados"))

    if session.get("usuario_id"):
        return redirect(url_for("main.home"))
    session.pop("cadastro", None)
    return render_template("cadastro_tipo.html")


@auth_bp.route("/cadastro/dados", methods=["GET", "POST"])
def cadastro_dados():
    cadastro = _cadastro_em_andamento("tipo")
    if cadastro is None:
        return redirect(url_for("auth.cadastro_tipo"))

    contexto = {
        "cidades": CIDADES_ES, "ddd": DDD_PADRAO,
        "etapa": 1, "total_etapas": _etapas(cadastro["tipo"]),
    }

    if request.method == "POST":
        dados, erro = validar_dados_pessoais(request.form)

        if erro is None and dados["cidade"] not in CIDADES_ES:
            erro = "Escolha uma cidade do Espírito Santo."
        if erro is None:
            conexao = get_connection()
            em_uso = conexao.execute("SELECT 1 FROM usuarios WHERE email = ?", (dados["email"],)).fetchone()
            conexao.close()
            if em_uso:
                erro = "Já existe uma conta com esse e-mail. Que tal entrar?"

        if erro:
            flash(erro, "erro")
            return render_template("cadastro_dados.html", dados=request.form, **contexto), 400

        # A sessão do Flask é um cookie ASSINADO, não criptografado: qualquer um com
        # acesso ao navegador consegue lê-lo. Por isso a senha vira hash aqui, na
        # primeira etapa, e o texto original nunca é gravado no cookie.
        cadastro.update(
            nome=dados["nome"], email=dados["email"], cidade=dados["cidade"],
            telefone=dados["telefone"], senha_hash=generate_password_hash(dados["senha"]),
        )
        session["cadastro"] = cadastro

        if cadastro["tipo"] == "candidato":
            return redirect(url_for("auth.cadastro_categoria"))
        return redirect(url_for("auth.cadastro_instrutor"))

    return render_template("cadastro_dados.html", dados=cadastro, **contexto)


@auth_bp.route("/cadastro/categoria", methods=["GET", "POST"])
def cadastro_categoria():
    cadastro = _cadastro_em_andamento("senha_hash")
    if cadastro is None or cadastro["tipo"] != "candidato":
        return redirect(url_for("auth.cadastro_tipo"))

    selecionadas = cadastro.get("categorias", [])

    if request.method == "POST":
        selecionadas = categorias_marcadas(request.form, "categorias")
        if not selecionadas:
            flash("Escolha pelo menos uma categoria de CNH.", "erro")
            return render_template("cadastro_categoria.html", categorias=CATEGORIAS_CNH,
                                   selecionadas=[], etapa=2, total_etapas=4), 400

        cadastro["categorias"] = selecionadas
        session["cadastro"] = cadastro
        return redirect(url_for("auth.cadastro_preferencias"))

    return render_template("cadastro_categoria.html", categorias=CATEGORIAS_CNH,
                           selecionadas=selecionadas, etapa=2, total_etapas=4)


@auth_bp.route("/cadastro/preferencias", methods=["GET", "POST"])
def cadastro_preferencias():
    cadastro = _cadastro_em_andamento("categorias")
    if cadastro is None:
        return redirect(url_for("auth.cadastro_tipo"))

    if request.method == "POST":
        for campo in ("prefere_instrutoras_mulheres", "prefere_experiencia_neurodivergencia",
                      "prefere_experiencia_pcd"):
            cadastro[campo] = campo in request.form
        session["cadastro"] = cadastro
        return redirect(url_for("auth.cadastro_acessibilidade"))

    return render_template("cadastro_preferencias.html", cadastro=cadastro, etapa=3, total_etapas=4)


@auth_bp.route("/cadastro/acessibilidade", methods=["GET", "POST"])
def cadastro_acessibilidade():
    cadastro = _cadastro_em_andamento("categorias", "prefere_instrutoras_mulheres")
    if cadastro is None:
        return redirect(url_for("auth.cadastro_tipo"))

    contexto = {"tipos_deficiencia": TIPOS_DEFICIENCIA, "canais": CANAIS_COMUNICACAO,
                "etapa": 4, "total_etapas": 4}

    if request.method != "POST":
        return render_template("cadastro_acessibilidade.html", **contexto)

    tipo_deficiencia = request.form.get("tipo_deficiencia", "")
    tipo_deficiencia = tipo_deficiencia if tipo_deficiencia in TIPOS_DEFICIENCIA else None
    canal = request.form.get("canal_comunicacao", "texto")
    canal = canal if canal in CANAIS_COMUNICACAO else "texto"
    precisa_veiculo_adaptado = "precisa_veiculo_adaptado" in request.form

    conexao = get_connection()
    try:
        cursor = conexao.execute(
            """
            INSERT INTO usuarios (nome, email, senha_hash, tipo, cidade, telefone)
            VALUES (?, ?, ?, 'candidato', ?, ?)
            """,
            (cadastro["nome"], cadastro["email"], cadastro["senha_hash"],
             cadastro["cidade"], cadastro["telefone"]),
        )
        usuario_id = cursor.lastrowid

        conexao.execute(
            """
            INSERT INTO preferencias_candidato
                (usuario_id, prefere_instrutoras_mulheres,
                 prefere_experiencia_neurodivergencia, prefere_experiencia_pcd)
            VALUES (?, ?, ?, ?)
            """,
            (usuario_id, int(cadastro["prefere_instrutoras_mulheres"]),
             int(cadastro["prefere_experiencia_neurodivergencia"]),
             int(cadastro["prefere_experiencia_pcd"])),
        )
        conexao.executemany(
            "INSERT INTO candidato_categorias (usuario_id, categoria) VALUES (?, ?)",
            [(usuario_id, categoria) for categoria in cadastro["categorias"]],
        )

        # Grava o perfil sempre que a pessoa informou algo. Antes, quem escolhia
        # "Libras" sem marcar um tipo de deficiência perdia essa preferência.
        if tipo_deficiencia or canal != "texto" or precisa_veiculo_adaptado:
            conexao.execute(
                """
                INSERT INTO perfis_acessibilidade
                    (usuario_id, tipo_deficiencia, canal_comunicacao, precisa_veiculo_adaptado)
                VALUES (?, ?, ?, ?)
                """,
                (usuario_id, tipo_deficiencia, canal, int(precisa_veiculo_adaptado)),
            )
        conexao.commit()
    except sqlite3.IntegrityError:
        conexao.rollback()
        flash("Já existe uma conta com esse e-mail.", "erro")
        return redirect(url_for("auth.cadastro_dados"))
    finally:
        conexao.close()

    iniciar_sessao({"id": usuario_id, "nome": cadastro["nome"], "tipo": "candidato"})
    flash("Conta criada. Bem-vindo(a) ao Habilita+!", "sucesso")
    return redirect(url_for("main.home"))


@auth_bp.route("/cadastro/instrutor", methods=["GET", "POST"])
def cadastro_instrutor():
    cadastro = _cadastro_em_andamento("senha_hash")
    if cadastro is None or cadastro["tipo"] != "instrutor":
        return redirect(url_for("auth.cadastro_tipo"))

    contexto = {"categorias": CATEGORIAS_CNH, "atendimentos": ATENDIMENTOS_INSTRUTOR,
                "etapa": 2, "total_etapas": 2}

    if request.method != "POST":
        return render_template("cadastro_instrutor.html", dados={}, **contexto)

    dados, erro = validar_perfil_profissional(request.form)
    if erro:
        flash(erro, "erro")
        return render_template("cadastro_instrutor.html", dados=dados, **contexto), 400

    conexao = get_connection()
    try:
        cursor = conexao.execute(
            """
            INSERT INTO usuarios (nome, email, senha_hash, tipo, cidade, telefone)
            VALUES (?, ?, ?, 'instrutor', ?, ?)
            """,
            (cadastro["nome"], cadastro["email"], cadastro["senha_hash"],
             cadastro["cidade"], cadastro["telefone"]),
        )
        usuario_id = cursor.lastrowid

        cursor = conexao.execute(
            """
            INSERT INTO instrutores
                (usuario_id, valor_aula, regiao_atuacao, verificado, atende_libras,
                 somente_mulheres, atende_neurodivergentes, atende_pcd, veiculo_adaptado_disponivel)
            VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (usuario_id, dados["valor_aula"], dados["regiao_atuacao"] or None,
             int(dados["atende_libras"]), int(dados["somente_mulheres"]),
             int(dados["atende_neurodivergentes"]), int(dados["atende_pcd"]),
             int(dados["veiculo_adaptado_disponivel"])),
        )
        conexao.executemany(
            "INSERT INTO instrutor_categorias (instrutor_id, categoria) VALUES (?, ?)",
            [(cursor.lastrowid, categoria) for categoria in dados["categorias"]],
        )
        conexao.commit()
    except sqlite3.IntegrityError:
        conexao.rollback()
        flash("Já existe uma conta com esse e-mail.", "erro")
        return redirect(url_for("auth.cadastro_dados"))
    finally:
        conexao.close()

    iniciar_sessao({"id": usuario_id, "nome": cadastro["nome"], "tipo": "instrutor"})
    flash("Perfil criado. Ele já aparece nas buscas, marcado como “Em análise” até a verificação.", "sucesso")
    return redirect(url_for("main.home"))
