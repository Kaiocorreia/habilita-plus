"""Regras de tempo e do ciclo de vida das aulas.

O servidor de produção roda em UTC. Sem fixar o fuso, às 21h de Vitória o
sistema já consideraria "amanhã" e liberaria ou bloquearia horários errados.
"""

from datetime import date, datetime, time, timedelta, timezone

# O Espírito Santo segue o horário de Brasília, que não tem horário de verão
# desde 2019. Um deslocamento fixo dispensa o pacote tzdata no Windows.
FUSO_BRASILIA = timezone(timedelta(hours=-3), "BRT")
DURACAO_AULA = timedelta(hours=1)

# Até quantos dias à frente uma aula pode ser marcada.
JANELA_AGENDAMENTO_DIAS = 90


def agora():
    return datetime.now(FUSO_BRASILIA)


def hoje():
    return agora().date()


def ler_data(texto):
    """Converte 'AAAA-MM-DD' em date; devolve None para qualquer entrada inválida."""
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def inicio_da_aula(dia, horario):
    return datetime.combine(dia, time.fromisoformat(horario), FUSO_BRASILIA)


def horario_ja_passou(dia, horario):
    return inicio_da_aula(dia, horario) <= agora()


def data_agendavel(dia):
    return dia is not None and hoje() <= dia <= hoje() + timedelta(days=JANELA_AGENDAMENTO_DIAS)


def concluir_aulas_passadas(conexao):
    """Marca como concluídas as aulas ativas que já terminaram.

    O status 'concluido' libera a avaliação. Antes, nada no sistema fazia essa
    transição: uma aula real ficava 'agendada' para sempre e nunca podia ser
    avaliada. A atualização roda sob demanda, nas telas que exibem aulas, e é
    idempotente: executá-la várias vezes produz o mesmo resultado.
    """
    terminou_ate = agora() - DURACAO_AULA
    conexao.execute(
        """
        UPDATE agendamentos
           SET status = 'concluido'
         WHERE status IN ('agendado', 'confirmado')
           AND (data < ? OR (data = ? AND horario <= ?))
        """,
        (
            terminou_ate.date().isoformat(),
            terminou_ate.date().isoformat(),
            terminou_ate.strftime("%H:%M"),
        ),
    )
    conexao.commit()


DIAS_DA_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_por_extenso(dia):
    """date(2026, 11, 25) -> 'quarta, 25 de novembro de 2026'."""
    return f"{DIAS_DA_SEMANA[dia.weekday()]}, {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def formatar_moeda(valor):
    """1234.5 -> 'R$ 1.234,50' (padrão brasileiro)."""
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"
