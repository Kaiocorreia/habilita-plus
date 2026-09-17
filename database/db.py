import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "instance" / "habilita.db"


def get_connection():
    # O Git não versiona pastas vazias, então 'instance/' não existe depois de um
    # clone. Sem ela, o sqlite3 falha com "unable to open database file".
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(DB_PATH)
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.row_factory = sqlite3.Row
    return conexao
