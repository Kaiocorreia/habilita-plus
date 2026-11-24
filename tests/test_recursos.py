"""Testes das funcionalidades da revisão: conta, salvos, folgas, remarcação,
calendário (.ics), prévia da página de entrada e otimização da conclusão de aulas."""

from datetime import timedelta

import tests.test_app as base
from app import agenda
from app.agenda import hoje
from database.db import get_connection

INSTRUTORA = base.INSTRUTORA


class TestConta(base.BaseTeste):
    def setUp(self):
        super().setUp()
        self.entrar(base.CANDIDATA)

    def test_atualizar_dados_muda_o_nome_no_topo(self):
        self.post("/conta/dados", {"nome": "Ana Paula Ferreira Lima", "telefone": "98877-6655", "cidade": "Serra"},
                  pagina_do_token="/conta")
        usuario = self.consultar("SELECT nome, telefone, cidade FROM usuarios WHERE email = ?", (base.CANDIDATA,))[0]
        self.assertEqual(tuple(usuario), ("Ana Paula Ferreira Lima", "27988776655", "Serra"))
        self.assertIn("Ana", self.cliente.get("/home").get_data(as_text=True))

    def test_trocar_senha_exige_a_atual(self):
        errada = self.post("/conta/senha", {"senha_atual": "errada", "senha_nova": "novasenha1",
                                            "senha_confirmacao": "novasenha1"}, pagina_do_token="/conta")
        self.assertEqual(errada.status_code, 400)
        self.post("/conta/senha", {"senha_atual": base.SENHA, "senha_nova": "novasenha1",
                                   "senha_confirmacao": "novasenha1"}, pagina_do_token="/conta")
        self.post("/logout", pagina_do_token="/home")
        self.assertIn("incorretos", self.entrar(base.CANDIDATA).get_data(as_text=True))
        self.assertTrue(self.entrar(base.CANDIDATA, "novasenha1").headers["Location"].endswith("/home"))

    def test_preferencias_mudam_a_busca(self):
        self.post("/conta/preferencias", {"categorias": ["B"], "canal_comunicacao": "texto"}, pagina_do_token="/conta")
        busca = self.cliente.get("/busca").get_data(as_text=True)
        self.assertNotIn("Aplicamos as preferências", busca)  # tirou "instrutoras mulheres" e Libras
        self.post("/conta/preferencias", {"categorias": ["B"], "prefere_instrutoras_mulheres": "on",
                                          "canal_comunicacao": "libras"}, pagina_do_token="/conta")
        self.assertIn("Aplicamos as preferências", self.cliente.get("/busca").get_data(as_text=True))

    def test_validacoes(self):
        for dados in ({"nome": "A", "cidade": "Serra"}, {"nome": "Ana Paula", "cidade": "Paris"},
                      {"nome": "Ana Paula", "cidade": "Serra", "telefone": "12"}):
            with self.subTest(dados=dados):
                self.assertEqual(self.post("/conta/dados", dados, pagina_do_token="/conta").status_code, 400)
        self.assertEqual(self.post("/conta/preferencias", {"categorias": []}, pagina_do_token="/conta").status_code, 400)


class TestSalvos(base.BaseTeste):
    def test_salvar_aparece_na_home_e_filtra_a_busca(self):
        self.entrar(base.CANDIDATA)
        carlos = self.id_instrutor("carlos.mendes@habilitaplus.com")
        self.post(f"/instrutor/{carlos}/salvar", pagina_do_token=f"/instrutor/{carlos}")
        self.assertIn("Seus salvos", self.cliente.get("/home").get_data(as_text=True))
        filtrada = self.cliente.get("/busca?salvos=on&ordenar=avaliacao").get_data(as_text=True)
        self.assertIn("Carlos Mendes", filtrada)
        self.assertNotIn("Juliana Oliveira", filtrada)

        self.post(f"/instrutor/{carlos}/salvar", pagina_do_token=f"/instrutor/{carlos}")  # alterna
        self.assertNotIn("Seus salvos", self.cliente.get("/home").get_data(as_text=True))

    def test_so_candidato_salva(self):
        self.entrar(INSTRUTORA)
        resposta = self.post(f"/instrutor/{self.id_instrutor()}/salvar", pagina_do_token="/home")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(len(self.consultar("SELECT 1 FROM favoritos")), 0)


class TestFolgas(base.BaseTeste):
    def test_folga_fecha_o_dia_para_agendamento(self):
        juliana, dia = self.id_instrutor(), self.dia_futuro(5)
        self.entrar(INSTRUTORA)
        self.post("/agenda/folgas", {"data": dia}, pagina_do_token="/agenda/folgas")
        self.assertIn("Sem aulas marcadas", self.cliente.get("/agenda/folgas").get_data(as_text=True))

        self.post("/logout", pagina_do_token="/home")
        self.entrar(base.CANDIDATA)
        pagina = self.cliente.get(f"/instrutor/{juliana}/agendar?data={dia}").get_data(as_text=True)
        self.assertIn("(folga)", pagina)
        self.assertNotIn('name="horario"', pagina)  # o dia não abre horários
        resposta = self.post(f"/instrutor/{juliana}/agendar", {"data": dia, "horario": "09:00"}, pagina_do_token="/home")
        self.assertNotIn("/agendamento/confirmar", resposta.headers["Location"])

        self.post("/logout", pagina_do_token="/home")
        self.entrar(INSTRUTORA)
        self.post(f"/agenda/folgas/{dia}/remover", pagina_do_token="/agenda/folgas")
        self.post("/logout", pagina_do_token="/home")
        self.entrar(base.CANDIDATA)
        self.assertIn("/sucesso", self.agendar(juliana, dia, "09:00").headers["Location"])

    def test_data_invalida(self):
        self.entrar(INSTRUTORA)
        for data in ("ontem", "2020-01-01", (hoje() + timedelta(days=500)).isoformat()):
            self.post("/agenda/folgas", {"data": data}, pagina_do_token="/agenda/folgas")
        self.assertEqual(len(self.consultar("SELECT 1 FROM folgas")), 0)


class TestRemarcar(base.BaseTeste):
    def setUp(self):
        super().setUp()
        self.juliana = self.id_instrutor()
        self.entrar(base.CANDIDATA)
        self.agendar(self.juliana, self.dia_futuro(3), "09:00")
        self.antiga = self.consultar("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["id"]

    def remarcar(self, data, horario):
        self.post(f"/instrutor/{self.juliana}/agendar", {"data": data, "horario": horario, "remarcar": self.antiga},
                  pagina_do_token=f"/instrutor/{self.juliana}/agendar?remarcar={self.antiga}")
        return self.post("/agendamento/confirmar", pagina_do_token="/agendamento/confirmar")

    def status(self, aula_id):
        return self.consultar("SELECT status FROM agendamentos WHERE id = ?", (aula_id,))[0]["status"]

    def test_remarcar_cancela_a_antiga_e_cria_a_nova(self):
        resposta = self.remarcar(self.dia_futuro(4), "11:00")
        self.assertIn("/sucesso", resposta.headers["Location"])
        self.assertEqual(self.status(self.antiga), "cancelado")
        nova = self.consultar("SELECT data, horario, status FROM agendamentos ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(tuple(nova), (self.dia_futuro(4), "11:00", "agendado"))

    def test_se_o_novo_horario_falhar_a_antiga_continua(self):
        # Outra pessoa pega o horário entre a revisão e a confirmação.
        self.post(f"/instrutor/{self.juliana}/agendar", {"data": self.dia_futuro(4), "horario": "13:00",
                                                        "remarcar": self.antiga}, pagina_do_token="/home")
        conexao = get_connection()
        conexao.execute("INSERT INTO agendamentos (candidato_id, instrutor_id, data, horario, valor) VALUES (6, ?, ?, '13:00', 90)",
                        (self.juliana, self.dia_futuro(4)))
        conexao.commit()
        conexao.close()
        resposta = self.post("/agendamento/confirmar", pagina_do_token="/home")
        self.assertNotIn("/sucesso", resposta.headers["Location"])
        self.assertEqual(self.status(self.antiga), "agendado")

    def test_telas_mantem_o_modo_remarcacao(self):
        escolha = self.cliente.get(f"/instrutor/{self.juliana}/agendar?remarcar={self.antiga}").get_data(as_text=True)
        self.assertIn("Remarcar aula", escolha)
        self.post(f"/instrutor/{self.juliana}/agendar", {"data": self.dia_futuro(4), "horario": "11:00",
                                                        "remarcar": self.antiga}, pagina_do_token="/home")
        revisao = self.cliente.get("/agendamento/confirmar").get_data(as_text=True)
        self.assertIn("Confirmar remarcação", revisao)
        self.assertIn(f"remarcar={self.antiga}", revisao)  # o link "Alterar" não perde a remarcação

    def test_nao_remarca_aula_de_outra_pessoa(self):
        self.post("/logout", pagina_do_token="/home")
        self.entrar(base.OUTRA_CANDIDATA)
        self.remarcar(self.dia_futuro(6), "15:00")
        self.assertEqual(self.status(self.antiga), "agendado")


class TestCalendario(base.BaseTeste):
    def test_arquivo_ics_da_aula(self):
        self.entrar(base.CANDIDATA)
        juliana = self.id_instrutor()
        self.agendar(juliana, self.dia_futuro(2), "14:00")
        aula = self.consultar("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["id"]
        resposta = self.cliente.get(f"/agendamento/{aula}/calendario.ics")
        texto = resposta.get_data(as_text=True)
        self.assertEqual(resposta.mimetype, "text/calendar")
        self.assertIn("BEGIN:VEVENT", texto)
        self.assertIn("Aula de direção com Juliana Oliveira", texto)
        # 14:00 em Brasília = 17:00 UTC
        self.assertIn(f"DTSTART:{self.dia_futuro(2).replace('-', '')}T170000Z", texto)
        self.assertIn("\r\n", texto)

        self.post("/logout", pagina_do_token="/home")
        self.entrar(base.OUTRA_CANDIDATA)
        self.assertEqual(self.cliente.get(f"/agendamento/{aula}/calendario.ics").status_code, 404)


class TestEntradaEOtimizacao(base.BaseTeste):
    def test_previa_usa_instrutor_e_precos_reais(self):
        html = self.cliente.get("/").get_data(as_text=True)
        self.assertIn("vitrine", html)
        self.assertIn("Juliana Oliveira", html)  # a mais bem avaliada entre as verificadas do seed

    def test_conclusao_de_aulas_respeita_o_intervalo(self):
        self.app.config["INTERVALO_CONCLUSAO"] = 60
        agenda._ultima_conclusao = float("-inf")
        self.entrar(base.CANDIDATA)
        self.cliente.get("/minhas-aulas")  # roda agora
        conexao = get_connection()
        cursor = conexao.execute(
            "INSERT INTO agendamentos (candidato_id, instrutor_id, data, horario, status, valor) VALUES (5, 1, ?, '08:00', 'agendado', 90)",
            ((hoje() - timedelta(days=2)).isoformat(),))
        conexao.commit()
        conexao.close()
        self.cliente.get("/minhas-aulas")  # dentro do intervalo: não roda de novo
        self.assertEqual(self.consultar("SELECT status FROM agendamentos WHERE id = ?", (cursor.lastrowid,))[0][0], "agendado")
        agenda._ultima_conclusao = float("-inf")
        self.cliente.get("/minhas-aulas")
        self.assertEqual(self.consultar("SELECT status FROM agendamentos WHERE id = ?", (cursor.lastrowid,))[0][0], "concluido")
