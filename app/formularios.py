"""Validação de formulários compartilhada entre cadastro e edição de perfil."""

import re

from app.constantes import ATENDIMENTOS_INSTRUTOR, CATEGORIAS_CNH, DDD_PADRAO, VALOR_AULA_MAXIMO

EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_MINIMA = 8


def normalizar_telefone(numero_digitado):
    """Guarda só dígitos, com o DDD 27 na frente. Devolve '' se vazio, None se inválido."""
    digitos = re.sub(r"\D", "", numero_digitado or "")
    if not digitos:
        return ""
    if digitos.startswith(DDD_PADRAO) and len(digitos) in (10, 11):
        digitos = digitos[len(DDD_PADRAO):]
    if len(digitos) not in (8, 9):
        return None
    return DDD_PADRAO + digitos


def categorias_marcadas(form, campo):
    # Filtra pela lista oficial: um valor forjado no formulário nunca chega ao banco.
    marcadas = form.getlist(campo)
    return [categoria for categoria in CATEGORIAS_CNH if categoria in marcadas]


def validar_dados_pessoais(form):
    """Devolve (dados, erro). 'dados' traz os campos já limpos."""
    dados = {
        "nome": " ".join(form.get("nome", "").split()),
        "email": form.get("email", "").strip().lower(),
        "senha": form.get("senha", ""),
        "cidade": form.get("cidade", ""),
        "telefone": normalizar_telefone(form.get("telefone", "")),
    }

    if len(dados["nome"]) < 3 or len(dados["nome"]) > 120:
        return dados, "Informe seu nome completo."
    if not EMAIL_VALIDO.match(dados["email"]) or len(dados["email"]) > 254:
        return dados, "Informe um e-mail válido, como nome@exemplo.com."
    if len(dados["senha"]) < SENHA_MINIMA:
        return dados, f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    if dados["telefone"] is None:
        return dados, "Informe o telefone com 8 ou 9 dígitos, sem o DDD."
    return dados, None


def validar_perfil_profissional(form):
    """Lê categorias, valor, região e atendimentos do instrutor. Devolve (dados, erro)."""
    dados = {
        "categorias": categorias_marcadas(form, "categorias_cnh"),
        "regiao_atuacao": " ".join(form.get("regiao_atuacao", "").split())[:80],
        "valor_texto": form.get("valor_aula", "").strip(),
    }
    for coluna, _rotulo, _descricao in ATENDIMENTOS_INSTRUTOR:
        dados[coluna] = coluna in form

    if not dados["categorias"]:
        return dados, "Escolha pelo menos uma categoria de CNH que você ensina."

    try:
        valor = float(dados["valor_texto"].replace("R$", "").replace(",", ".").strip())
    except ValueError:
        return dados, "Informe um valor de aula válido, por exemplo 90,00."
    if not 1 <= valor <= VALOR_AULA_MAXIMO:
        return dados, f"O valor da aula deve ficar entre R$ 1 e R$ {VALOR_AULA_MAXIMO}."

    dados["valor_aula"] = round(valor, 2)
    return dados, None
