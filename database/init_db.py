import os
from pathlib import Path

try:
    from database.db import DB_PATH, get_connection
except ImportError:  # executado como script: python database/init_db.py
    from db import DB_PATH, get_connection

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
