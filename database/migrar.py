"""Atualiza a estrutura de um banco que já existe, sem perder dados.

O init_db.py apaga tudo e recria; serve para começar do zero. Este script é o
caminho para o banco de produção, que tem cadastros reais: aplica só o que
falta e não mexe em nada que já está atualizado. Rodar duas vezes é seguro.

    python database/migrar.py

O app também chama migrar() ao iniciar, então um "git pull + Reload" basta.
Antes de qualquer alteração, uma cópia do banco é salva ao lado do original.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

try:
    from database.db import DB_PATH, get_connection
except ImportError:  # executado como script: python database/migrar.py
    from db import DB_PATH, get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

TABELAS_NOVAS = """
CREATE TABLE IF NOT EXISTS configuracoes (
    chave           TEXT PRIMARY KEY,
    valor           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acoes_gerenciais (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gerente_id      INTEGER NOT NULL,
    acao            TEXT NOT NULL,
    alvo            TEXT NOT NULL,
    detalhe         TEXT,
    data            TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (gerente_id) REFERENCES usuarios (id)
);
CREATE INDEX IF NOT EXISTS idx_acoes_gerenciais_data ON acoes_gerenciais (data);

-- Instrutores salvos pelo candidato (N:N entre usuários e instrutores).
CREATE TABLE IF NOT EXISTS favoritos (
    usuario_id      INTEGER NOT NULL,
    instrutor_id    INTEGER NOT NULL,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (usuario_id, instrutor_id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
    FOREIGN KEY (instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE
);

-- Dias de folga: o instrutor não recebe agendamentos nessas datas.
CREATE TABLE IF NOT EXISTS folgas (
    instrutor_id    INTEGER NOT NULL,
    data            TEXT NOT NULL,
    PRIMARY KEY (instrutor_id, data),
    FOREIGN KEY (instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE
);
"""


def _colunas(conexao, tabela):
    return {linha["name"] for linha in conexao.execute(f"PRAGMA table_info({tabela})")}


def _sql_da_tabela(conexao, tabela):
    linha = conexao.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)
    ).fetchone()
    return linha["sql"] if linha else None


def _create_usuarios_do_schema():
    """O CREATE TABLE usuarios atual, lido do schema.sql (fonte única da verdade)."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    return re.search(r"CREATE TABLE usuarios \(.*?\n\);", schema, flags=re.S).group(0)


def pendencias(conexao):
    """Lista o que falta aplicar. Vazia quando o banco já está atualizado."""
    if _sql_da_tabela(conexao, "usuarios") is None:
        return []  # banco vazio: quem cria é o init_db.py
    faltando = []
    if "'gerente'" not in _sql_da_tabela(conexao, "usuarios"):
        faltando.append("usuarios aceitar o tipo 'gerente'")
    if "ativo" not in _colunas(conexao, "instrutores"):
        faltando.append("instrutores.ativo")
    if "oculta" not in _colunas(conexao, "avaliacoes"):
        faltando.append("avaliacoes.oculta")
    for tabela in ("configuracoes", "acoes_gerenciais", "favoritos", "folgas"):
        if _sql_da_tabela(conexao, tabela) is None:
            faltando.append(f"tabela {tabela}")
    return faltando


def _reconstruir_usuarios(conexao):
    """Troca a restrição CHECK de usuarios.tipo, que o SQLite não altera em vigor.

    Segue o procedimento documentado pelo SQLite: com as chaves estrangeiras
    desligadas, cria a tabela nova, copia os dados, apaga a antiga e renomeia.
    Os IDs são copiados como estão, então agendamentos e avaliações continuam
    apontando para as mesmas pessoas.
    """
    create_novo = _create_usuarios_do_schema().replace(
        "CREATE TABLE usuarios", "CREATE TABLE usuarios_migracao", 1
    )
    colunas = ", ".join(sorted(_colunas(conexao, "usuarios")))
    conexao.execute(create_novo)
    conexao.execute(f"INSERT INTO usuarios_migracao ({colunas}) SELECT {colunas} FROM usuarios")
    conexao.execute("DROP TABLE usuarios")
    conexao.execute("ALTER TABLE usuarios_migracao RENAME TO usuarios")


def migrar(silencioso=False):
    """Aplica o que estiver pendente. Devolve a lista do que foi feito."""
    if not DB_PATH.exists():
        return []

    conexao = get_connection()
    faltando = pendencias(conexao)
    if not faltando:
        conexao.close()
        return []

    copia = DB_PATH.with_name(f"{DB_PATH.stem}-antes-da-migracao-{datetime.now():%Y%m%d-%H%M%S}.db")
    shutil.copy2(DB_PATH, copia)

    # Transações controladas à mão (sem o BEGIN automático do módulo sqlite3).
    conexao.isolation_level = None
    # Chaves estrangeiras desligadas durante a reconstrução (exigência do
    # SQLite), e conferidas no fim: se algo ficasse órfão, nada é gravado.
    conexao.execute("PRAGMA foreign_keys = OFF")
    try:
        conexao.execute("BEGIN IMMEDIATE")
        if "usuarios aceitar o tipo 'gerente'" in faltando:
            _reconstruir_usuarios(conexao)
        if "instrutores.ativo" in faltando:
            conexao.execute(
                "ALTER TABLE instrutores ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))"
            )
        if "avaliacoes.oculta" in faltando:
            conexao.execute(
                "ALTER TABLE avaliacoes ADD COLUMN oculta INTEGER NOT NULL DEFAULT 0 CHECK (oculta IN (0, 1))"
            )
        # Um comando por vez: executescript() faria um COMMIT implícito no meio.
        for comando in filter(str.strip, TABELAS_NOVAS.split(";")):
            conexao.execute(comando)

        orfaos = conexao.execute("PRAGMA foreign_key_check").fetchall()
        if orfaos:
            raise RuntimeError(f"Migração cancelada: {len(orfaos)} referência(s) quebrada(s).")
        conexao.execute("COMMIT")
    except Exception:
        conexao.execute("ROLLBACK")
        conexao.close()
        raise
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.close()

    if not silencioso:
        print(f"Cópia de segurança: {copia}")
        for item in faltando:
            print(f"  aplicado: {item}")
    return faltando


if __name__ == "__main__":
    feito = migrar()
    if not feito:
        print("Nada a fazer: o banco já está atualizado.")
