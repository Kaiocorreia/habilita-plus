import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# HABILITA_DB_PATH permite apontar para outro arquivo (os testes usam um banco
# temporário, assim nunca tocam no banco real).
DB_PATH = Path(os.environ.get("HABILITA_DB_PATH") or BASE_DIR / "instance" / "habilita.db")


def get_connection():
    # O Git não versiona pastas vazias, então 'instance/' não existe depois de um
    # clone. Sem ela, o sqlite3 falha com "unable to open database file".
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(DB_PATH)
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.row_factory = sqlite3.Row
    return conexao
