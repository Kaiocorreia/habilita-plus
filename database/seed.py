from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from db import get_connection

SENHA_PADRAO = generate_password_hash("senha123")

TABELAS_EM_ORDEM_DE_LIMPEZA = [
    "avaliacoes",
    "agendamentos",
    "instrutor_categorias",
    "candidato_categorias",
    "instrutor_veiculos",
    "veiculos",
    "instrutores",
    "perfis_acessibilidade",
    "preferencias_candidato",
    "usuarios",
]


def limpar_tabelas(conexao):
    for tabela in TABELAS_EM_ORDEM_DE_LIMPEZA:
        conexao.execute(f"DELETE FROM {tabela}")
    placeholders = ", ".join("?" for _ in TABELAS_EM_ORDEM_DE_LIMPEZA)
    conexao.execute(
        f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
        TABELAS_EM_ORDEM_DE_LIMPEZA,
    )


def inserir_usuario(conexao, nome, email, tipo, cidade, telefone, foto_url=None):
    cursor = conexao.execute(
        """
        INSERT INTO usuarios (nome, email, senha_hash, tipo, cidade, telefone, foto_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (nome, email, SENHA_PADRAO, tipo, cidade, telefone, foto_url),
    )
    return cursor.lastrowid


def inserir_veiculo(conexao, marca, modelo, categoria_cnh, transmissao, adaptado, valor_locacao, imagem):
    cursor = conexao.execute(
        """
        INSERT INTO veiculos (marca, modelo, categoria_cnh, transmissao, adaptado, valor_locacao, imagem)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (marca, modelo, categoria_cnh, transmissao, int(adaptado), valor_locacao, imagem),
    )
    return cursor.lastrowid


def vincular_veiculo(conexao, instrutor_id, veiculo_id):
    conexao.execute(
        "INSERT INTO instrutor_veiculos (instrutor_id, veiculo_id) VALUES (?, ?)",
        (instrutor_id, veiculo_id),
    )


def inserir_perfil_acessibilidade(conexao, usuario_id, tipo_deficiencia, canal_comunicacao, precisa_veiculo_adaptado):
    conexao.execute(
        """
        INSERT INTO perfis_acessibilidade
            (usuario_id, tipo_deficiencia, canal_comunicacao, precisa_veiculo_adaptado)
        VALUES (?, ?, ?, ?)
        """,
        (usuario_id, tipo_deficiencia, canal_comunicacao, int(precisa_veiculo_adaptado)),
    )


def inserir_instrutor(conexao, usuario_id, categorias_cnh, valor_aula, regiao_atuacao,
                       verificado, atende_libras, somente_mulheres,
                       atende_neurodivergentes, atende_pcd, veiculo_adaptado_disponivel):
    cursor = conexao.execute(
        """
        INSERT INTO instrutores
            (usuario_id, valor_aula, regiao_atuacao,
             verificado, atende_libras, somente_mulheres,
             atende_neurodivergentes, atende_pcd, veiculo_adaptado_disponivel)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (usuario_id, valor_aula, regiao_atuacao,
         int(verificado), int(atende_libras), int(somente_mulheres),
         int(atende_neurodivergentes), int(atende_pcd), int(veiculo_adaptado_disponivel)),
    )
    instrutor_id = cursor.lastrowid

    conexao.executemany(
        "INSERT INTO instrutor_categorias (instrutor_id, categoria) VALUES (?, ?)",
        [(instrutor_id, c) for c in categorias_cnh.split(",")],
    )
    return instrutor_id


def inserir_preferencia_candidato(conexao, usuario_id, categorias_cnh_pretendidas,
                                  prefere_instrutoras_mulheres,
                                  prefere_experiencia_neurodivergencia=False,
                                  prefere_experiencia_pcd=False):
    conexao.execute(
        """
        INSERT INTO preferencias_candidato
            (usuario_id, prefere_instrutoras_mulheres,
             prefere_experiencia_neurodivergencia, prefere_experiencia_pcd)
        VALUES (?, ?, ?, ?)
        """,
        (usuario_id, int(prefere_instrutoras_mulheres),
         int(prefere_experiencia_neurodivergencia), int(prefere_experiencia_pcd)),
    )
    conexao.executemany(
        "INSERT INTO candidato_categorias (usuario_id, categoria) VALUES (?, ?)",
        [(usuario_id, c) for c in categorias_cnh_pretendidas.split(",")],
    )


def inserir_agendamento(conexao, candidato_id, instrutor_id, data_aula, horario, status, valor,
                        veiculo_id=None, valor_locacao=0.0):
    cursor = conexao.execute(
        """
        INSERT INTO agendamentos
            (candidato_id, instrutor_id, veiculo_id, data, horario, status, valor, valor_locacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (candidato_id, instrutor_id, veiculo_id, data_aula, horario, status, valor, valor_locacao),
    )
    return cursor.lastrowid


def inserir_avaliacao(conexao, agendamento_id, candidato_id, instrutor_id, nota, comentario):
    conexao.execute(
        """
        INSERT INTO avaliacoes (agendamento_id, candidato_id, instrutor_id, nota, comentario)
        VALUES (?, ?, ?, ?, ?)
        """,
        (agendamento_id, candidato_id, instrutor_id, nota, comentario),
    )


def semear():
    conexao = get_connection()
    limpar_tabelas(conexao)

    hoje = date.today()

    juliana_usuario_id = inserir_usuario(
        conexao, "Juliana Oliveira", "juliana.oliveira@habilitaplus.com",
        "instrutor", "Vitória", "27999990001", "img/instrutores/juliana.jpg",
    )
    juliana_instrutor_id = inserir_instrutor(
        conexao, juliana_usuario_id, categorias_cnh="A,B", valor_aula=90.00,
        regiao_atuacao="Grande Vitória", verificado=True, atende_libras=True,
        somente_mulheres=True, atende_neurodivergentes=True, atende_pcd=True,
        veiculo_adaptado_disponivel=True,
    )

    fernanda_usuario_id = inserir_usuario(
        conexao, "Fernanda Souza", "fernanda.souza@habilitaplus.com",
        "instrutor", "Vila Velha", "27999990002", "img/instrutores/fernanda.jpg",
    )
    fernanda_instrutor_id = inserir_instrutor(
        conexao, fernanda_usuario_id, categorias_cnh="A,B,C", valor_aula=85.00,
        regiao_atuacao="Vila Velha", verificado=True, atende_libras=True,
        somente_mulheres=True, atende_neurodivergentes=False, atende_pcd=True,
        veiculo_adaptado_disponivel=False,
    )

    carlos_usuario_id = inserir_usuario(
        conexao, "Carlos Mendes", "carlos.mendes@habilitaplus.com",
        "instrutor", "Vitória", "27999990003", "img/instrutores/carlos.jpg",
    )
    carlos_instrutor_id = inserir_instrutor(
        conexao, carlos_usuario_id, categorias_cnh="B", valor_aula=70.00,
        regiao_atuacao="Vitória", verificado=True, atende_libras=False,
        somente_mulheres=False, atende_neurodivergentes=True, atende_pcd=False,
        veiculo_adaptado_disponivel=False,
    )

    roberto_usuario_id = inserir_usuario(
        conexao, "Roberto Almeida", "roberto.almeida@habilitaplus.com",
        "instrutor", "Serra", "27999990004", "img/instrutores/roberto.jpg",
    )
    roberto_instrutor_id = inserir_instrutor(
        conexao, roberto_usuario_id, categorias_cnh="B,D", valor_aula=100.00,
        regiao_atuacao="Serra", verificado=False, atende_libras=False,
        somente_mulheres=False, atende_neurodivergentes=False, atende_pcd=False,
        veiculo_adaptado_disponivel=False,
    )

    mobi_id = inserir_veiculo(
        conexao, "Fiat", "Mobi Like", categoria_cnh="B", transmissao="manual",
        adaptado=False, valor_locacao=25.00, imagem="img/veiculos/hatch.svg",
    )
    onix_id = inserir_veiculo(
        conexao, "Chevrolet", "Onix 1.0", categoria_cnh="B", transmissao="manual",
        adaptado=False, valor_locacao=35.00, imagem="img/veiculos/hatch.svg",
    )
    hb20_id = inserir_veiculo(
        conexao, "Hyundai", "HB20 Automático", categoria_cnh="B", transmissao="automatico",
        adaptado=False, valor_locacao=45.00, imagem="img/veiculos/sedan.svg",
    )
    kwid_id = inserir_veiculo(
        conexao, "Renault", "Kwid Adaptado", categoria_cnh="B", transmissao="automatico",
        adaptado=True, valor_locacao=55.00, imagem="img/veiculos/adaptado.svg",
    )
    biz_id = inserir_veiculo(
        conexao, "Honda", "Biz 110i", categoria_cnh="A", transmissao="manual",
        adaptado=False, valor_locacao=20.00, imagem="img/veiculos/moto.svg",
    )

    for veiculo_id in (mobi_id, onix_id, hb20_id, kwid_id, biz_id):
        vincular_veiculo(conexao, juliana_instrutor_id, veiculo_id)

    for veiculo_id in (onix_id, hb20_id, biz_id):
        vincular_veiculo(conexao, fernanda_instrutor_id, veiculo_id)

    for veiculo_id in (mobi_id, onix_id):
        vincular_veiculo(conexao, carlos_instrutor_id, veiculo_id)

    vincular_veiculo(conexao, roberto_instrutor_id, onix_id)

    ana_paula_id = inserir_usuario(
        conexao, "Ana Paula Ferreira", "ana.paula@example.com",
        "candidato", "Vitória", "27988880001",
    )
    inserir_perfil_acessibilidade(
        conexao, ana_paula_id, tipo_deficiencia="Surdez ou deficiência auditiva",
        canal_comunicacao="libras", precisa_veiculo_adaptado=False,
    )
    inserir_preferencia_candidato(
        conexao, ana_paula_id, categorias_cnh_pretendidas="B",
        prefere_instrutoras_mulheres=True, prefere_experiencia_pcd=True,
    )

    mariana_id = inserir_usuario(
        conexao, "Mariana Costa", "mariana.costa@example.com",
        "candidato", "Vila Velha", "27988880002",
    )
    inserir_preferencia_candidato(
        conexao, mariana_id, categorias_cnh_pretendidas="A,B",
        prefere_instrutoras_mulheres=True,
    )

    pedro_id = inserir_usuario(
        conexao, "Pedro Henrique", "pedro.henrique@example.com",
        "candidato", "Vitória", "27988880003",
    )
    inserir_preferencia_candidato(
        conexao, pedro_id, categorias_cnh_pretendidas="B",
        prefere_instrutoras_mulheres=False, prefere_experiencia_neurodivergencia=True,
    )

    aula_ana_paula = inserir_agendamento(
        conexao, ana_paula_id, juliana_instrutor_id,
        data_aula=(hoje - timedelta(days=10)).isoformat(), horario="14:00",
        status="concluido", valor=90.00, veiculo_id=onix_id, valor_locacao=35.00,
    )
    inserir_avaliacao(
        conexao, aula_ana_paula, ana_paula_id, juliana_instrutor_id,
        nota=5, comentario="Excelente profissional! Muito paciente e explicou tudo em Libras.",
    )

    aula_mariana = inserir_agendamento(
        conexao, mariana_id, juliana_instrutor_id,
        data_aula=(hoje - timedelta(days=3)).isoformat(), horario="09:00",
        status="concluido", valor=90.00, veiculo_id=hb20_id, valor_locacao=45.00,
    )
    inserir_avaliacao(
        conexao, aula_mariana, mariana_id, juliana_instrutor_id,
        nota=5, comentario="Aula tranquila, recomendo demais.",
    )

    aula_pedro_carlos = inserir_agendamento(
        conexao, pedro_id, carlos_instrutor_id,
        data_aula=(hoje - timedelta(days=5)).isoformat(), horario="16:00",
        status="concluido", valor=70.00, veiculo_id=mobi_id, valor_locacao=25.00,
    )
    inserir_avaliacao(
        conexao, aula_pedro_carlos, pedro_id, carlos_instrutor_id,
        nota=4, comentario="Bom instrutor, mas atrasou um pouco.",
    )

    inserir_agendamento(
        conexao, pedro_id, fernanda_instrutor_id,
        data_aula=(hoje + timedelta(days=2)).isoformat(), horario="10:00",
        status="agendado", valor=85.00, veiculo_id=biz_id, valor_locacao=20.00,
    )

    conexao.commit()
    conexao.close()
    print("Seed concluído: 4 instrutores, 3 candidatos, 5 veículos, 4 agendamentos, 3 avaliações.")


if __name__ == "__main__":
    semear()
