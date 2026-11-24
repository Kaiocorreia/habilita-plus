"""Minha conta: dados pessoais, senha e preferências de quem está logado."""

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.constantes import CANAIS_COMUNICACAO, CATEGORIAS_CNH, CIDADES_ES, DDD_PADRAO, TIPOS_DEFICIENCIA
from app.formularios import SENHA_MINIMA, categorias_marcadas, normalizar_telefone
from app.sessao import exige_login
from database.db import get_connection

conta_bp = Blueprint("conta", __name__)

# A conta de gerente exige mais (mesma regra do database/criar_gerente.py).
SENHA_MINIMA_GERENTE = 10

PREFERENCIAS = [
    ("prefere_instrutoras_mulheres", "Prefiro instrutoras mulheres"),
    ("prefere_experiencia_neurodivergencia", "Experiência com neurodivergência"),
    ("prefere_experiencia_pcd", "Experiência com pessoas com deficiência"),
]


def _dados_da_conta(conexao, usuario_id):
    usuario = conexao.execute(
        "SELECT id, nome, email, tipo, cidade, telefone FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    extras = {}
    if usuario["tipo"] == "candidato":
        extras["preferencias"] = conexao.execute(
            "SELECT * FROM preferencias_candidato WHERE usuario_id = ?", (usuario_id,)
        ).fetchone()
        extras["acessibilidade"] = conexao.execute(
            "SELECT * FROM perfis_acessibilidade WHERE usuario_id = ?", (usuario_id,)
        ).fetchone()
        extras["categorias_pretendidas"] = [linha["categoria"] for linha in conexao.execute(
            "SELECT categoria FROM candidato_categorias WHERE usuario_id = ? ORDER BY categoria", (usuario_id,)
        )]
    return usuario, extras


def _pagina(conexao, status=200):
    usuario, extras = _dados_da_conta(conexao, g.usuario["id"])
    conexao.close()
    telefone = usuario["telefone"] or ""
    return render_template(
        "conta.html", usuario=usuario, telefone_local=telefone[len(DDD_PADRAO):] if telefone else "",
        cidades=CIDADES_ES, ddd=DDD_PADRAO, categorias=CATEGORIAS_CNH, preferencias_opcoes=PREFERENCIAS,
        tipos_deficiencia=TIPOS_DEFICIENCIA, canais=CANAIS_COMUNICACAO,
        senha_minima=SENHA_MINIMA_GERENTE if usuario["tipo"] == "gerente" else SENHA_MINIMA, **extras,
    ), status


@conta_bp.route("/conta")
@exige_login()
def minha_conta():
    return _pagina(get_connection())


@conta_bp.route("/conta/dados", methods=["POST"])
@exige_login()
def salvar_dados():
    nome = " ".join(request.form.get("nome", "").split())
    telefone = normalizar_telefone(request.form.get("telefone", ""))
    cidade = request.form.get("cidade", "")
    conexao = get_connection()

    erro = None
    if not 3 <= len(nome) <= 120:
        erro = "Informe seu nome completo."
    elif telefone is None:
        erro = "Informe o celular com 8 ou 9 dígitos, sem o DDD."
    elif g.usuario["tipo"] != "gerente" and cidade not in CIDADES_ES:
        erro = "Escolha uma cidade do Espírito Santo."
    if erro:
        flash(erro, "erro")
        return _pagina(conexao, 400)

    conexao.execute("UPDATE usuarios SET nome = ?, telefone = ?, cidade = ? WHERE id = ?",
                    (nome, telefone or None, cidade or None, g.usuario["id"]))
    conexao.commit()
    conexao.close()
    session["usuario_nome"] = nome  # o nome aparece no topo da página
    flash("Dados atualizados.", "sucesso")
    return redirect(url_for("conta.minha_conta"))


@conta_bp.route("/conta/senha", methods=["POST"])
@exige_login()
def trocar_senha():
    atual = request.form.get("senha_atual", "")
    nova = request.form.get("senha_nova", "")
    confirmacao = request.form.get("senha_confirmacao", "")
    minimo = SENHA_MINIMA_GERENTE if g.usuario["tipo"] == "gerente" else SENHA_MINIMA

    conexao = get_connection()
    hash_atual = conexao.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (g.usuario["id"],)).fetchone()[0]

    erro = None
    if not check_password_hash(hash_atual, atual):
        erro = "A senha atual não confere."
    elif len(nova) < minimo:
        erro = f"A nova senha precisa ter pelo menos {minimo} caracteres."
    elif nova != confirmacao:
        erro = "A confirmação não é igual à nova senha."
    elif nova == atual:
        erro = "A nova senha precisa ser diferente da atual."
    if erro:
        flash(erro, "erro")
        return _pagina(conexao, 400)

    conexao.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (generate_password_hash(nova), g.usuario["id"]))
    conexao.commit()
    conexao.close()
    flash("Senha alterada. Use a nova senha no próximo login.", "sucesso")
    return redirect(url_for("conta.minha_conta"))


@conta_bp.route("/conta/preferencias", methods=["POST"])
@exige_login(tipo="candidato")
def salvar_preferencias():
    categorias = categorias_marcadas(request.form, "categorias")
    tipo_deficiencia = request.form.get("tipo_deficiencia", "")
    tipo_deficiencia = tipo_deficiencia if tipo_deficiencia in TIPOS_DEFICIENCIA else None
    canal = request.form.get("canal_comunicacao", "texto")
    canal = canal if canal in CANAIS_COMUNICACAO else "texto"
    precisa_adaptado = "precisa_veiculo_adaptado" in request.form

    conexao = get_connection()
    if not categorias:
        flash("Escolha pelo menos uma categoria de CNH.", "erro")
        return _pagina(conexao, 400)

    usuario_id = g.usuario["id"]
    valores = [int(campo in request.form) for campo, _rotulo in PREFERENCIAS]
    # UPSERT: contas antigas podem não ter a linha de preferências ainda.
    conexao.execute(
        """
        INSERT INTO preferencias_candidato (usuario_id, prefere_instrutoras_mulheres,
               prefere_experiencia_neurodivergencia, prefere_experiencia_pcd)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(usuario_id) DO UPDATE SET
            prefere_instrutoras_mulheres = excluded.prefere_instrutoras_mulheres,
            prefere_experiencia_neurodivergencia = excluded.prefere_experiencia_neurodivergencia,
            prefere_experiencia_pcd = excluded.prefere_experiencia_pcd
        """,
        (usuario_id, *valores),
    )
    conexao.execute("DELETE FROM candidato_categorias WHERE usuario_id = ?", (usuario_id,))
    conexao.executemany("INSERT INTO candidato_categorias (usuario_id, categoria) VALUES (?, ?)",
                        [(usuario_id, c) for c in categorias])

    if tipo_deficiencia or canal != "texto" or precisa_adaptado:
        conexao.execute(
            """
            INSERT INTO perfis_acessibilidade (usuario_id, tipo_deficiencia, canal_comunicacao, precisa_veiculo_adaptado)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(usuario_id) DO UPDATE SET tipo_deficiencia = excluded.tipo_deficiencia,
                canal_comunicacao = excluded.canal_comunicacao,
                precisa_veiculo_adaptado = excluded.precisa_veiculo_adaptado
            """,
            (usuario_id, tipo_deficiencia, canal, int(precisa_adaptado)),
        )
    else:
        conexao.execute("DELETE FROM perfis_acessibilidade WHERE usuario_id = ?", (usuario_id,))
    conexao.commit()
    conexao.close()
    flash("Preferências salvas. A busca já usa as novas escolhas.", "sucesso")
    return redirect(url_for("conta.minha_conta"))
