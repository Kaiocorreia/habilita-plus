"""Cria (ou redefine a senha de) uma conta de gerente.

    python database/criar_gerente.py email@exemplo.com "Nome Completo"

A senha é pedida no console e não aparece na tela nem fica no histórico.
Não há cadastro de gerente pelo site, de propósito: se houvesse, qualquer
pessoa poderia se cadastrar como gerente.
"""

import getpass
import sys

from werkzeug.security import generate_password_hash

try:
    from database.db import get_connection
    from database.migrar import migrar
except ImportError:  # executado como script
    from db import get_connection
    from migrar import migrar

SENHA_MINIMA = 10


def criar_gerente(email, nome, senha):
    email = email.strip().lower()
    if "@" not in email or len(nome.strip()) < 3:
        raise ValueError("Informe um e-mail válido e o nome completo.")
    if len(senha) < SENHA_MINIMA:
        raise ValueError(f"A senha do gerente precisa de pelo menos {SENHA_MINIMA} caracteres.")

    migrar(silencioso=True)  # garante que o banco já aceita o tipo 'gerente'
    conexao = get_connection()
    existente = conexao.execute("SELECT id, tipo FROM usuarios WHERE email = ?", (email,)).fetchone()

    if existente and existente["tipo"] != "gerente":
        conexao.close()
        raise ValueError("Esse e-mail já pertence a um candidato ou instrutor. Use outro e-mail.")

    if existente:
        conexao.execute("UPDATE usuarios SET senha_hash = ?, nome = ? WHERE id = ?",
                        (generate_password_hash(senha), nome.strip(), existente["id"]))
        resultado = "Senha do gerente redefinida."
    else:
        conexao.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (?, ?, ?, 'gerente')",
            (nome.strip(), email, generate_password_hash(senha)),
        )
        resultado = "Conta de gerente criada."
    conexao.commit()
    conexao.close()
    return resultado


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    senha = getpass.getpass("Senha do gerente: ")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")
    try:
        print(criar_gerente(sys.argv[1], sys.argv[2], senha))
    except ValueError as erro:
        sys.exit(str(erro))
