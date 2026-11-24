"""Configurações da plataforma editáveis pela gerência.

Ficam na tabela `configuracoes` (chave -> texto). Quando uma chave não existe,
vale o padrão abaixo: um banco novo funciona sem nenhuma configuração gravada.
"""

from flask import g, has_app_context

from app.constantes import HORARIOS_DISPONIVEIS
from database.db import get_connection

# Horários que a gerência pode oferecer (de hora em hora).
HORARIOS_POSSIVEIS = [f"{hora:02d}:00" for hora in range(6, 22)]
JANELA_MINIMA, JANELA_MAXIMA = 7, 180
AVISO_MAXIMO = 240

PADROES = {
    "horarios": ",".join(HORARIOS_DISPONIVEIS),
    "janela_dias": "90",
    "aviso_texto": "",
    "aviso_ativo": "0",
}


def _ler_do_banco():
    conexao = get_connection()
    try:
        linhas = conexao.execute("SELECT chave, valor FROM configuracoes").fetchall()
    except Exception:  # tabela ainda não migrada: usa só os padrões
        linhas = []
    conexao.close()
    brutos = dict(PADROES, **{linha["chave"]: linha["valor"] for linha in linhas})

    horarios = [h for h in brutos["horarios"].split(",") if h in HORARIOS_POSSIVEIS]
    try:
        janela = min(max(int(brutos["janela_dias"]), JANELA_MINIMA), JANELA_MAXIMA)
    except ValueError:
        janela = int(PADROES["janela_dias"])

    return {
        "horarios": horarios or list(HORARIOS_DISPONIVEIS),
        "janela_dias": janela,
        "aviso_texto": brutos["aviso_texto"],
        "aviso_ativo": brutos["aviso_ativo"] == "1" and bool(brutos["aviso_texto"].strip()),
    }


def configuracoes():
    """Configurações atuais, lidas uma vez por requisição."""
    if has_app_context():
        if "configuracoes" not in g:
            g.configuracoes = _ler_do_banco()
        return g.configuracoes
    return _ler_do_banco()


def salvar(conexao, valores):
    """Grava várias chaves de uma vez (INSERT ou UPDATE). Não faz commit."""
    conexao.executemany(
        "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        list(valores.items()),
    )
    g.pop("configuracoes", None)
