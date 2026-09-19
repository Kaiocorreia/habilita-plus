import re
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.constantes import CATEGORIAS_CNH, CIDADES_ES, DDD_PADRAO
from database.db import get_connection

auth_bp = Blueprint("auth", __name__)


def normalizar_telefone(numero_digitado):
    digitos = re.sub(r"\D", "", numero_digitado)
    if not digitos:
        return ""
    return DDD_PADRAO + digitos


def categorias_selecionadas(campo):
    return [c for c in CATEGORIAS_CNH if c in request.form.getlist(campo)]


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        conexao = get_connection()
        usuario = conexao.execute(
            "SELECT id, nome, senha_hash, tipo FROM usuarios WHERE email = ?",
            (email,),
        ).fetchone()
        conexao.close()

        if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
            flash("E-mail ou senha incorretos.", "erro")
            return render_template("login.html", email=email)

        session["usuario_id"] = usuario["id"]
        session["usuario_nome"] = usuario["nome"]
        session["usuario_tipo"] = usuario["tipo"]
        return redirect(url_for("main.home"))

    return render_template("login.html", email="")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro_tipo():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        if tipo not in ("candidato", "instrutor"):
            flash("Escolha uma das opções para continuar.", "erro")
            return render_template("cadastro_tipo.html")

        session["cadastro"] = {"tipo": tipo}
        return redirect(url_for("auth.cadastro_dados"))

    session.pop("cadastro", None)
    return render_template("cadastro_tipo.html")


@auth_bp.route("/cadastro/dados", methods=["GET", "POST"])
def cadastro_dados():
    cadastro = session.get("cadastro")
    if not cadastro:
        return redirect(url_for("auth.cadastro_tipo"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        cidade = request.form.get("cidade", "")
        telefone = normalizar_telefone(request.form.get("telefone", ""))

        erro = None
        if not nome or not email or not senha:
            erro = "Nome, e-mail e senha são obrigatórios."
        elif len(senha) < 6:
            erro = "A senha precisa ter pelo menos 6 caracteres."
        elif cidade not in CIDADES_ES:
            erro = "Escolha uma cidade do Espírito Santo."
        else:
            conexao = get_connection()
            email_em_uso = conexao.execute(
                "SELECT id FROM usuarios WHERE email = ?", (email,)
            ).fetchone()
            conexao.close()
            if email_em_uso:
                erro = "Já existe uma conta cadastrada com esse e-mail."

        if erro:
            flash(erro, "erro")
            return render_template("cadastro_dados.html", dados=request.form, cidades=CIDADES_ES, ddd=DDD_PADRAO)

        cadastro.update(nome=nome, email=email, senha=senha, cidade=cidade, telefone=telefone)
        session["cadastro"] = cadastro

        if cadastro["tipo"] == "candidato":
            return redirect(url_for("auth.cadastro_categoria"))
        return redirect(url_for("auth.cadastro_instrutor"))

    return render_template("cadastro_dados.html", dados={}, cidades=CIDADES_ES, ddd=DDD_PADRAO)


@auth_bp.route("/cadastro/categoria", methods=["GET", "POST"])
def cadastro_categoria():
    cadastro = session.get("cadastro")
    if not cadastro or "email" not in cadastro:
        return redirect(url_for("auth.cadastro_tipo"))

    if request.method == "POST":
        categorias = categorias_selecionadas("categorias")
        if not categorias:
            flash("Escolha pelo menos uma categoria de CNH.", "erro")
            return render_template("cadastro_categoria.html", categorias=CATEGORIAS_CNH)

        cadastro["categorias_cnh_pretendidas"] = ",".join(categorias)
        session["cadastro"] = cadastro
        return redirect(url_for("auth.cadastro_preferencias"))

    return render_template("cadastro_categoria.html", categorias=CATEGORIAS_CNH)


@auth_bp.route("/cadastro/preferencias", methods=["GET", "POST"])
def cadastro_preferencias():
    cadastro = session.get("cadastro")
    if not cadastro or "categorias_cnh_pretendidas" not in cadastro:
        return redirect(url_for("auth.cadastro_tipo"))

    if request.method == "POST":
        cadastro["prefere_instrutoras_mulheres"] = "prefere_instrutoras_mulheres" in request.form
        cadastro["prefere_experiencia_neurodivergencia"] = "prefere_experiencia_neurodivergencia" in request.form
        cadastro["prefere_experiencia_pcd"] = "prefere_experiencia_pcd" in request.form
        session["cadastro"] = cadastro
        return redirect(url_for("auth.cadastro_acessibilidade"))

    return render_template("cadastro_preferencias.html")


@auth_bp.route("/cadastro/acessibilidade", methods=["GET", "POST"])
def cadastro_acessibilidade():
    cadastro = session.get("cadastro")
    if not cadastro or "prefere_instrutoras_mulheres" not in cadastro:
        return redirect(url_for("auth.cadastro_tipo"))

    if request.method == "POST":
        tipo_deficiencia = request.form.get("tipo_deficiencia", "nenhuma")
        canal_comunicacao = request.form.get("canal_comunicacao") or None
        precisa_veiculo_adaptado = "precisa_veiculo_adaptado" in request.form

        conexao = get_connection()
        try:
            cursor = conexao.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, tipo, cidade, telefone)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cadastro["nome"], cadastro["email"],
                    generate_password_hash(cadastro["senha"]),
                    "candidato", cadastro["cidade"], cadastro["telefone"],
                ),
            )
            usuario_id = cursor.lastrowid

            conexao.execute(
                """
                INSERT INTO preferencias_candidato
                    (usuario_id, prefere_instrutoras_mulheres,
                     prefere_experiencia_neurodivergencia, prefere_experiencia_pcd)
                VALUES (?, ?, ?, ?)
                """,
                (
                    usuario_id,
                    int(cadastro["prefere_instrutoras_mulheres"]),
                    int(cadastro["prefere_experiencia_neurodivergencia"]),
                    int(cadastro["prefere_experiencia_pcd"]),
                ),
            )
            conexao.executemany(
                "INSERT INTO candidato_categorias (usuario_id, categoria) VALUES (?, ?)",
                [(usuario_id, c) for c in cadastro["categorias_cnh_pretendidas"].split(",")],
            )

            if tipo_deficiencia != "nenhuma":
                conexao.execute(
                    """
                    INSERT INTO perfis_acessibilidade
                        (usuario_id, tipo_deficiencia, canal_comunicacao, precisa_veiculo_adaptado)
                    VALUES (?, ?, ?, ?)
                    """,
                    (usuario_id, tipo_deficiencia, canal_comunicacao, int(precisa_veiculo_adaptado)),
                )

            conexao.commit()
        except sqlite3.IntegrityError:
            conexao.rollback()
            flash("Já existe uma conta cadastrada com esse e-mail.", "erro")
            return redirect(url_for("auth.cadastro_dados"))
        finally:
            conexao.close()

        session.pop("cadastro", None)
        flash("Cadastro concluído! Faça login para continuar.", "sucesso")
        return redirect(url_for("auth.login"))

    return render_template("cadastro_acessibilidade.html")


@auth_bp.route("/cadastro/instrutor", methods=["GET", "POST"])
def cadastro_instrutor():
    cadastro = session.get("cadastro")
    if not cadastro or "email" not in cadastro:
        return redirect(url_for("auth.cadastro_tipo"))

    if request.method == "POST":
        categorias = categorias_selecionadas("categorias_cnh")
        valor_aula = request.form.get("valor_aula", "")
        regiao_atuacao = request.form.get("regiao_atuacao", "").strip()
        atende_libras = "atende_libras" in request.form
        somente_mulheres = "somente_mulheres" in request.form
        atende_neurodivergentes = "atende_neurodivergentes" in request.form
        atende_pcd = "atende_pcd" in request.form
        veiculo_adaptado_disponivel = "veiculo_adaptado_disponivel" in request.form

        erro = None
        if not categorias:
            erro = "Escolha pelo menos uma categoria de CNH que você ensina."
        elif not valor_aula:
            erro = "Informe o valor da sua aula."
        else:
            try:
                valor_aula = float(valor_aula.replace(",", "."))
                if valor_aula <= 0:
                    erro = "O valor da aula precisa ser maior que zero."
            except ValueError:
                erro = "Informe um valor de aula válido, por exemplo 90.00."

        if erro:
            flash(erro, "erro")
            return render_template("cadastro_instrutor.html", categorias=CATEGORIAS_CNH)

        conexao = get_connection()
        try:
            cursor = conexao.execute(
                """
                INSERT INTO usuarios (nome, email, senha_hash, tipo, cidade, telefone)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cadastro["nome"], cadastro["email"],
                    generate_password_hash(cadastro["senha"]),
                    "instrutor", cadastro["cidade"], cadastro["telefone"],
                ),
            )
            usuario_id = cursor.lastrowid

            cursor = conexao.execute(
                """
                INSERT INTO instrutores
                    (usuario_id, valor_aula, regiao_atuacao,
                     verificado, atende_libras, somente_mulheres,
                     atende_neurodivergentes, atende_pcd, veiculo_adaptado_disponivel)
                VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    usuario_id, valor_aula, regiao_atuacao,
                    int(atende_libras), int(somente_mulheres),
                    int(atende_neurodivergentes), int(atende_pcd), int(veiculo_adaptado_disponivel),
                ),
            )
            conexao.executemany(
                "INSERT INTO instrutor_categorias (instrutor_id, categoria) VALUES (?, ?)",
                [(cursor.lastrowid, c) for c in categorias],
            )
            conexao.commit()
        except sqlite3.IntegrityError:
            conexao.rollback()
            flash("Já existe uma conta cadastrada com esse e-mail.", "erro")
            return redirect(url_for("auth.cadastro_dados"))
        finally:
            conexao.close()

        session.pop("cadastro", None)
        flash("Cadastro concluído! Sua conta passará por verificação antes de aparecer nas buscas.", "sucesso")
        return redirect(url_for("auth.login"))

    return render_template("cadastro_instrutor.html", categorias=CATEGORIAS_CNH)
