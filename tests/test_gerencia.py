"""Testes da área de gerência: acesso, e o impacto de cada ação no site."""

import re
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

import tests.test_app as base  # define o banco temporário antes de importar o app
from app.agenda import hoje
from database import db as modulo_db
from database import migrar as modulo_migrar
from database.criar_gerente import criar_gerente
from database.db import get_connection

GERENTE = "gerente@habilitaplus.com"
ROBERTO = "roberto.almeida@habilitaplus.com"  # instrutor "Em análise" no seed


class BaseGerencia(base.BaseTeste):
    def post_gerencia(self, caminho, dados=None):
        return self.post(caminho, dados, pagina_do_token="/gerencia")

    def como_gerente(self):
        self.post("/logout", pagina_do_token="/home")
        self.entrar(GERENTE)

    def como(self, email):
        self.post("/logout", pagina_do_token="/home")
        self.entrar(email)


class TestAcesso(BaseGerencia):
    PAGINAS = ("/gerencia", "/gerencia/instrutores", "/gerencia/avaliacoes", "/gerencia/veiculos",
               "/gerencia/veiculos/novo", "/gerencia/configuracoes", "/gerencia/registro")

    def test_so_gerente_entra(self):
        for email in (None, base.CANDIDATA, base.INSTRUTORA):
            if email:
                self.como(email)
            for caminho in self.PAGINAS:
                with self.subTest(usuario=email, caminho=caminho):
                    self.assertEqual(self.cliente.get(caminho).status_code, 302)

    def test_gerente_ve_todas_as_paginas(self):
        self.entrar(GERENTE)
        for caminho in self.PAGINAS:
            with self.subTest(caminho=caminho):
                self.assertEqual(self.cliente.get(caminho).status_code, 200)
        self.assertIn("/gerencia", self.cliente.get("/home").headers["Location"])

    def test_login_volta_para_a_pagina_com_os_filtros(self):
        resposta = self.cliente.get("/gerencia/instrutores?filtro=todos")
        self.assertIn("filtro%3Dtodos", resposta.headers["Location"])
        destino = self.post("/login", {"email": GERENTE, "senha": base.SENHA,
                                       "proximo": "/gerencia/instrutores?filtro=todos"})
        self.assertTrue(destino.headers["Location"].endswith("/gerencia/instrutores?filtro=todos"))

    def test_nao_existe_cadastro_de_gerente_pelo_site(self):
        resposta = self.post("/cadastro", {"tipo": "gerente"}, pagina_do_token="/cadastro")
        self.assertEqual(resposta.status_code, 400)


class TestInstrutores(BaseGerencia):
    def setUp(self):
        super().setUp()
        self.roberto = self.id_instrutor(ROBERTO)
        self.entrar(GERENTE)

    def test_aprovar_mostra_selo_no_site_e_registra(self):
        perfil = lambda: self.cliente.get(f"/instrutor/{self.roberto}").get_data(as_text=True)
        self.assertIn("Em análise", perfil())
        self.post_gerencia(f"/gerencia/instrutores/{self.roberto}/aprovar")
        self.assertIn("Verificado", perfil())
        self.assertEqual(self.consultar("SELECT verificado FROM instrutores WHERE id = ?", (self.roberto,))[0][0], 1)
        registro = self.consultar("SELECT acao, alvo FROM acoes_gerenciais")
        self.assertEqual([tuple(r) for r in registro], [("Aprovou", "Roberto Almeida")])

    def test_suspender_tira_das_buscas_e_bloqueia_agendamento(self):
        juliana = self.id_instrutor()
        self.post_gerencia(f"/gerencia/instrutores/{juliana}/suspender")

        self.como(base.CANDIDATA)
        busca = self.cliente.get("/busca?ordenar=avaliacao").get_data(as_text=True)
        self.assertNotIn("Juliana Oliveira", busca)
        self.assertNotIn("Juliana Oliveira", self.cliente.get("/home").get_data(as_text=True))
        self.assertEqual(self.cliente.get(f"/instrutor/{juliana}").status_code, 404)
        resposta = self.post(f"/instrutor/{juliana}/agendar", {"data": self.dia_futuro(), "horario": "09:00"},
                             pagina_do_token="/home")
        self.assertIn("/busca", resposta.headers["Location"])

        self.como(base.INSTRUTORA)
        self.assertIn("suspenso", self.cliente.get("/home").get_data(as_text=True))

        self.como_gerente()
        self.post_gerencia(f"/gerencia/instrutores/{juliana}/reativar")
        self.como(base.CANDIDATA)
        self.assertIn("Juliana Oliveira", self.cliente.get("/busca?ordenar=avaliacao").get_data(as_text=True))

    def test_acao_invalida_e_redirecionamento_externo(self):
        self.assertEqual(self.post_gerencia(f"/gerencia/instrutores/{self.roberto}/apagar").status_code, 404)
        self.assertEqual(self.post_gerencia("/gerencia/instrutores/9999/aprovar").status_code, 404)
        resposta = self.post_gerencia(f"/gerencia/instrutores/{self.roberto}/aprovar", {"voltar": "//evil.com"})
        self.assertNotIn("evil.com", resposta.headers["Location"])

    def test_filtros_e_busca(self):
        pendentes = self.cliente.get("/gerencia/instrutores?filtro=pendentes").get_data(as_text=True)
        self.assertIn("Roberto Almeida", pendentes)
        self.assertNotIn("Juliana Oliveira", pendentes)
        self.assertIn("Juliana", self.cliente.get("/gerencia/instrutores?filtro=todos&q=juliana").get_data(as_text=True))


class TestAvaliacoes(BaseGerencia):
    def test_ocultar_recalcula_a_media_e_restaurar_volta(self):
        juliana = self.id_instrutor()
        nota_baixa = self.consultar(
            "SELECT id, comentario FROM avaliacoes WHERE instrutor_id = ? ORDER BY nota LIMIT 1", (juliana,))[0]
        media = lambda: self.consultar(
            "SELECT ROUND(AVG(nota), 1) FROM avaliacoes WHERE instrutor_id = ? AND oculta = 0", (juliana,))[0][0]
        antes = media()

        self.entrar(GERENTE)
        self.post_gerencia(f"/gerencia/avaliacoes/{nota_baixa['id']}/ocultar")
        perfil = self.cliente.get(f"/instrutor/{juliana}").get_data(as_text=True)
        if nota_baixa["comentario"]:
            self.assertNotIn(nota_baixa["comentario"], perfil)
        self.assertGreaterEqual(media(), antes)
        self.assertIn(nota_baixa["comentario"] or "Sem comentário",
                      self.cliente.get("/gerencia/avaliacoes?filtro=ocultas").get_data(as_text=True))

        self.post_gerencia(f"/gerencia/avaliacoes/{nota_baixa['id']}/restaurar")
        self.assertEqual(media(), antes)


class TestVeiculos(BaseGerencia):
    def test_cadastrar_e_vincular_aparece_no_perfil_e_no_agendamento(self):
        roberto = self.id_instrutor(ROBERTO)
        self.entrar(GERENTE)
        resposta = self.post_gerencia("/gerencia/veiculos/novo", {
            "marca": "Toyota", "modelo": "Yaris Teste", "categoria_cnh": "B", "transmissao": "automatico",
            "valor_locacao": "42,50", "imagem": "img/veiculos/sedan.svg", "instrutores": [str(roberto)],
        })
        self.assertEqual(resposta.status_code, 302)
        veiculo = self.consultar("SELECT id, valor_locacao FROM veiculos WHERE modelo = 'Yaris Teste'")[0]
        self.assertEqual(veiculo["valor_locacao"], 42.5)
        self.assertIn("Yaris Teste", self.cliente.get(f"/instrutor/{roberto}").get_data(as_text=True))

        self.post_gerencia(f"/gerencia/veiculos/{veiculo['id']}", {
            "marca": "Toyota", "modelo": "Yaris Teste", "categoria_cnh": "B", "transmissao": "automatico",
            "valor_locacao": "50", "imagem": "img/veiculos/sedan.svg", "instrutores": [str(roberto)],
        })
        self.como(base.CANDIDATA)
        agendar = self.cliente.get(f"/instrutor/{roberto}/agendar?data={self.dia_futuro()}").get_data(as_text=True)
        self.assertIn("Yaris Teste", agendar)
        self.assertIn("50,00", agendar)

    def test_validacao_do_veiculo(self):
        self.entrar(GERENTE)
        resposta = self.post_gerencia("/gerencia/veiculos/novo", {
            "marca": "", "modelo": "X", "categoria_cnh": "Z", "transmissao": "voador",
            "valor_locacao": "abc", "imagem": "../../segredo.txt"})
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(len(self.consultar("SELECT 1 FROM veiculos WHERE modelo = 'X'")), 0)


class TestConfiguracoes(BaseGerencia):
    def salvar(self, **campos):
        dados = {"horarios": ["08:00", "19:00"], "janela_dias": "90", "aviso_texto": "", **campos}
        return self.post_gerencia("/gerencia/configuracoes", dados)

    def test_horarios_mudam_o_agendamento(self):
        self.entrar(GERENTE)
        self.salvar()
        self.como(base.CANDIDATA)
        juliana, data = self.id_instrutor(), self.dia_futuro()
        pagina = self.cliente.get(f"/instrutor/{juliana}/agendar?data={data}").get_data(as_text=True)
        self.assertIn('value="19:00"', pagina)
        self.assertNotIn('value="09:00"', pagina)
        recusado = self.post(f"/instrutor/{juliana}/agendar", {"data": data, "horario": "09:00"},
                             pagina_do_token="/home")
        self.assertNotIn("/agendamento/confirmar", recusado.headers["Location"])
        self.assertIn("/sucesso", self.agendar(juliana, data, "19:00").headers["Location"])

    def test_janela_limita_o_calendario(self):
        self.entrar(GERENTE)
        self.salvar(janela_dias="7")
        self.como(base.CANDIDATA)
        longe = (hoje() + timedelta(days=30)).isoformat()
        resposta = self.post(f"/instrutor/{self.id_instrutor()}/agendar", {"data": longe, "horario": "08:00"},
                             pagina_do_token="/home")
        self.assertNotIn("/agendamento/confirmar", resposta.headers["Location"])

    def test_aviso_aparece_em_todas_as_paginas(self):
        self.entrar(GERENTE)
        self.salvar(aviso_texto="Sem aulas no feriado de 25/12.", aviso_ativo="on")
        self.post("/logout", pagina_do_token="/gerencia")
        self.assertIn("Sem aulas no feriado", self.cliente.get("/").get_data(as_text=True))
        self.assertIn("Sem aulas no feriado", self.cliente.get("/login").get_data(as_text=True))

        self.entrar(GERENTE)
        self.salvar(aviso_texto="Sem aulas no feriado de 25/12.")  # desmarcado
        self.assertNotIn("Sem aulas no feriado", self.cliente.get("/gerencia/registro").get_data(as_text=True).split("<main")[0])

    def test_validacoes(self):
        self.entrar(GERENTE)
        for campos in ({"horarios": []}, {"janela_dias": "500"}, {"janela_dias": "x"},
                       {"aviso_ativo": "on", "aviso_texto": ""}, {"aviso_texto": "a" * 300}):
            with self.subTest(campos=campos):
                self.assertEqual(self.salvar(**campos).status_code, 400)


class TestMigracao(base.BaseTeste):
    def test_banco_no_formato_antigo_e_migrado_sem_perda(self):
        atual = Path("database/schema.sql").read_text(encoding="utf-8")
        antigo = atual.replace(", 'gerente')", ")")
        antigo = re.sub(r"\n\s*-- 0 = suspenso.*?\n\s*ativo .*?\n", "\n", antigo)
        antigo = re.sub(r"\n\s*-- 1 = ocultada.*?\n\s*oculta .*?\n", "\n", antigo)
        antigo = re.sub(r"-- Configurações da plataforma.*?(?=-- Índice PARCIAL)", "", antigo, flags=re.S)
        antigo = antigo.replace("CREATE INDEX idx_acoes_gerenciais_data ON acoes_gerenciais (data);", "")
        self.assertNotIn("gerente", antigo)

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "antigo.db"
            conexao = sqlite3.connect(caminho)
            conexao.executescript(antigo)
            conexao.execute("INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES ('Ana', 'ana@x.com', 'h', 'candidato')")
            conexao.commit()
            conexao.close()

            # O caminho é lido em dois módulos: migrar (cópia de segurança) e db (conexão).
            originais = (modulo_migrar.DB_PATH, modulo_db.DB_PATH)
            modulo_migrar.DB_PATH = modulo_db.DB_PATH = caminho
            try:
                feito = modulo_migrar.migrar(silencioso=True)
                self.assertEqual(len(feito), 5)
                self.assertEqual(modulo_migrar.migrar(silencioso=True), [])
            finally:
                modulo_migrar.DB_PATH, modulo_db.DB_PATH = originais

            conexao = sqlite3.connect(caminho)
            self.assertEqual(conexao.execute("SELECT email FROM usuarios").fetchall(), [("ana@x.com",)])
            conexao.execute("INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES ('G', 'g@x.com', 'h', 'gerente')")
            self.assertEqual(conexao.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            conexao.close()
            self.assertEqual(len(list(Path(pasta).glob("antigo-antes-da-migracao-*.db"))), 1)


class TestCriarGerente(base.BaseTeste):
    def test_cria_e_entra(self):
        criar_gerente("chefe@habilitaplus.com", "Chefe da Gerência", "uma-senha-forte")
        self.entrar("chefe@habilitaplus.com", "uma-senha-forte")
        self.assertEqual(self.cliente.get("/gerencia").status_code, 200)

    def test_recusa_senha_fraca_e_email_de_outra_conta(self):
        with self.assertRaises(ValueError):
            criar_gerente("novo@x.com", "Novo Gerente", "curta")
        with self.assertRaises(ValueError):
            criar_gerente(base.CANDIDATA, "Tentativa", "uma-senha-forte")
        tipo = self.consultar("SELECT tipo FROM usuarios WHERE email = ?", (base.CANDIDATA,))[0][0]
        self.assertEqual(tipo, "candidato")
