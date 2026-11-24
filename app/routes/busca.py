from flask import Blueprint, g, render_template, request

from app.constantes import CATEGORIAS_CNH, CIDADES_ES
from app.consultas import ORDEM_RELEVANCIA, SELECT_INSTRUTORES
from app.sessao import exige_login
from database.db import get_connection

busca_bp = Blueprint("busca", __name__)

ORDENACOES = {
    "avaliacao": ORDEM_RELEVANCIA,
    "menor_preco": "i.valor_aula ASC, " + ORDEM_RELEVANCIA,
    "maior_preco": "i.valor_aula DESC, " + ORDEM_RELEVANCIA,
}

# Filtro da tela -> coluna booleana em instrutores. O nome da coluna vem desta
# lista fixa, nunca do usuário, então montá-lo no SQL é seguro.
FILTROS_DE_ATENDIMENTO = {
    "somente_mulheres": "i.somente_mulheres",
    "libras": "i.atende_libras",
    "neurodivergentes": "i.atende_neurodivergentes",
    "pcd": "i.atende_pcd",
    "veiculo_adaptado": "i.veiculo_adaptado_disponivel",
}


def _numero(texto, minimo, maximo):
    """Converte texto em número dentro da faixa; qualquer outra coisa vira None."""
    try:
        valor = float(str(texto).replace(",", "."))
    except ValueError:
        return None
    return valor if minimo <= valor <= maximo else None


def preferencias_salvas(usuario_id):
    conexao = get_connection()
    preferencias = conexao.execute(
        """
        SELECT prefere_instrutoras_mulheres, prefere_experiencia_neurodivergencia,
               prefere_experiencia_pcd
        FROM preferencias_candidato WHERE usuario_id = ?
        """,
        (usuario_id,),
    ).fetchone()
    acessibilidade = conexao.execute(
        "SELECT canal_comunicacao, precisa_veiculo_adaptado FROM perfis_acessibilidade WHERE usuario_id = ?",
        (usuario_id,),
    ).fetchone()
    conexao.close()

    salvas = {}
    if preferencias:
        salvas.update(
            somente_mulheres=bool(preferencias["prefere_instrutoras_mulheres"]),
            neurodivergentes=bool(preferencias["prefere_experiencia_neurodivergencia"]),
            pcd=bool(preferencias["prefere_experiencia_pcd"]),
        )
    if acessibilidade:
        salvas.update(
            libras=acessibilidade["canal_comunicacao"] == "libras",
            veiculo_adaptado=bool(acessibilidade["precisa_veiculo_adaptado"]),
        )
    return salvas


def ler_filtros(argumentos):
    """Lê os filtros da URL descartando valores fora do esperado."""
    cidade = argumentos.get("cidade", "")
    categoria = argumentos.get("categoria", "")
    ordenar = argumentos.get("ordenar", "avaliacao")
    preco = _numero(argumentos.get("preco_maximo", ""), 1, 10000)
    nota = _numero(argumentos.get("nota_minima", ""), 1, 5)

    filtros = {
        "q": " ".join(argumentos.get("q", "").split())[:60],
        "cidade": cidade if cidade in CIDADES_ES else "",
        "categoria": categoria if categoria in CATEGORIAS_CNH else "",
        "preco_maximo": f"{preco:g}" if preco else "",
        "nota_minima": f"{nota:g}" if nota else "",
        "ordenar": ordenar if ordenar in ORDENACOES else "avaliacao",
    }
    for chave in FILTROS_DE_ATENDIMENTO:
        filtros[chave] = chave in argumentos
    return filtros


def montar_consulta(filtros):
    # Perfis ainda não verificados também aparecem (marcados como "Em análise"),
    # senão quem acabou de se cadastrar como instrutor ficaria invisível no site.
    condicoes = ["i.ativo = 1"]
    parametros = []

    if filtros["q"]:
        # O texto digitado entra como parâmetro (?), nunca concatenado no SQL.
        condicoes.append("(u.nome LIKE ? OR i.regiao_atuacao LIKE ? OR u.cidade LIKE ?)")
        parametros += [f"%{filtros['q']}%"] * 3

    if filtros["cidade"]:
        condicoes.append("u.cidade = ?")
        parametros.append(filtros["cidade"])

    if filtros["categoria"]:
        # Comparação exata pela tabela de junção. Antes era um LIKE '%B%', que só
        # funcionava por acaso: as categorias são letras únicas.
        condicoes.append(
            "EXISTS (SELECT 1 FROM instrutor_categorias ic"
            "         WHERE ic.instrutor_id = i.id AND ic.categoria = ?)"
        )
        parametros.append(filtros["categoria"])

    if filtros["preco_maximo"]:
        condicoes.append("i.valor_aula <= ?")
        parametros.append(float(filtros["preco_maximo"]))

    for chave, coluna in FILTROS_DE_ATENDIMENTO.items():
        if filtros[chave]:
            condicoes.append(f"{coluna} = 1")

    sql = SELECT_INSTRUTORES + " WHERE " + " AND ".join(condicoes) + " GROUP BY i.id"

    # HAVING, e não WHERE: a média só existe depois do GROUP BY.
    if filtros["nota_minima"]:
        sql += " HAVING AVG(a.nota) >= ?"
        parametros.append(float(filtros["nota_minima"]))

    sql += " ORDER BY " + ORDENACOES[filtros["ordenar"]]
    return sql, parametros


@busca_bp.route("/busca")
@exige_login()
def buscar():
    filtros = ler_filtros(request.args)

    # Na primeira visita (sem nenhum filtro na URL), aplica as preferências que a
    # pessoa marcou no cadastro: quem pediu atendimento em Libras não precisa
    # pedir de novo.
    preferencias_aplicadas = False
    if not request.args and g.usuario["tipo"] == "candidato":
        salvas = preferencias_salvas(g.usuario["id"])
        if any(salvas.values()):
            filtros.update(salvas)
            preferencias_aplicadas = True

    sql, parametros = montar_consulta(filtros)
    conexao = get_connection()
    instrutores = conexao.execute(sql, parametros).fetchall()
    conexao.close()

    filtros_ativos = sum(
        1 for chave in ("q", "cidade", "categoria", "preco_maximo", "nota_minima") if filtros[chave]
    ) + sum(1 for chave in FILTROS_DE_ATENDIMENTO if filtros[chave])

    return render_template(
        "busca.html",
        instrutores=instrutores,
        filtros=filtros,
        filtros_ativos=filtros_ativos,
        preferencias_aplicadas=preferencias_aplicadas,
        cidades=CIDADES_ES,
        categorias=CATEGORIAS_CNH,
    )
