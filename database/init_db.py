import os
from pathlib import Path

from db import get_connection, DB_PATH

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def criar_banco():
    if DB_PATH.exists():
        os.remove(DB_PATH)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as arquivo:
        schema_sql = arquivo.read()

    conexao = get_connection()
    conexao.executescript(schema_sql)
    conexao.commit()
    conexao.close()
    print(f"Banco de dados criado em: {DB_PATH}")


if __name__ == "__main__":
    criar_banco()
