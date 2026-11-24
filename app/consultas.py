"""Consultas SQL compartilhadas entre telas.

A listagem de instrutores aparece na home, na busca e no perfil. Antes, o mesmo
SELECT estava copiado em três arquivos; uma mudança em um deles (como a
normalização das categorias) precisava ser repetida à mão nos outros dois.
"""

# A subconsulta correlacionada evita juntar instrutor_categorias com avaliacoes
# no mesmo JOIN: isso multiplicaria as linhas e inflaria o COUNT das avaliações.
SELECT_INSTRUTORES = """
    SELECT i.id,
           u.nome,
           u.cidade,
           u.foto_url,
           (SELECT GROUP_CONCAT(categoria, ', ')
              FROM (SELECT categoria FROM instrutor_categorias
                     WHERE instrutor_id = i.id ORDER BY categoria)) AS categorias_cnh,
           i.valor_aula,
           i.regiao_atuacao,
           i.verificado,
           i.atende_libras,
           i.somente_mulheres,
           i.atende_neurodivergentes,
           i.atende_pcd,
           i.veiculo_adaptado_disponivel,
           i.ativo,
           ROUND(AVG(a.nota), 1) AS media_estrelas,
           COUNT(a.id)           AS total_avaliacoes
    FROM instrutores i
    JOIN usuarios u ON u.id = i.usuario_id
    -- Avaliações ocultadas pela moderação ficam fora da média e da contagem.
    LEFT JOIN avaliacoes a ON a.instrutor_id = i.id AND a.oculta = 0
"""

# Verificados primeiro; entre eles, melhor nota. "(media IS NULL)" joga quem
# ainda não tem avaliação para o fim sem depender de NULLS LAST.
ORDEM_RELEVANCIA = (
    "i.verificado DESC, (media_estrelas IS NULL), media_estrelas DESC, total_avaliacoes DESC"
)

VEICULOS_DO_INSTRUTOR = """
    SELECT v.id, v.marca, v.modelo, v.categoria_cnh, v.transmissao, v.adaptado,
           v.valor_locacao, v.imagem
    FROM veiculos v
    JOIN instrutor_veiculos iv ON iv.veiculo_id = v.id
    WHERE iv.instrutor_id = ?
    ORDER BY v.valor_locacao ASC
"""

# Aulas com os dados das duas partes, para as telas de candidato e de instrutor.
SELECT_AULAS = """
    SELECT ag.id,
           ag.data,
           ag.horario,
           ag.status,
           ag.valor,
           ag.valor_locacao,
           strftime('%d/%m/%Y', ag.data) AS data_formatada,
           i.id         AS instrutor_id,
           ui.nome      AS nome_instrutor,
           ui.foto_url  AS foto_instrutor,
           ui.telefone  AS telefone_instrutor,
           uc.nome      AS nome_candidato,
           uc.foto_url  AS foto_candidato,
           uc.telefone  AS telefone_candidato,
           av.id        AS avaliacao_id,
           v.marca,
           v.modelo
    FROM agendamentos ag
    JOIN instrutores i  ON i.id = ag.instrutor_id
    JOIN usuarios ui    ON ui.id = i.usuario_id
    JOIN usuarios uc    ON uc.id = ag.candidato_id
    LEFT JOIN avaliacoes av ON av.agendamento_id = ag.id
    LEFT JOIN veiculos v    ON v.id = ag.veiculo_id
"""
