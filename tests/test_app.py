"""Testes automatizados do Habilita+.

Rodar:  python -m unittest discover -s tests -v

Cada teste usa um banco temporário recriado do zero com o seed, então nunca
toca no banco real em instance/habilita.db.
"""

import contextlib
import io
import os
import re
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

# Precisa vir antes de importar o app: database/db.py lê o caminho na importação.
_PASTA_TEMPORARIA = tempfile.TemporaryDirectory()
os.environ["HABILITA_DB_PATH"] = str(Path(_PASTA_TEMPORARIA.name) / "teste.db")
os.environ.pop("HABILITA_SECRET_KEY", None)

from app import create_app  # noqa: E402
from app.agenda import agora, hoje  # noqa: E402
from database.db import get_connection  # noqa: E402
from database.init_db import criar_banco  # noqa: E402
from database.seed import semear  # noqa: E402

SENHA = "senha123"
CANDIDATA = "ana.paula@example.com"
OUTRA_CANDIDATA = "mariana.costa@example.com"
INSTRUTORA = "juliana.oliveira@habilitaplus.com"


def extrair_token(html):
    encontrado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return encontrado.group(1) if encontrado else None


class BaseTeste(unittest.TestCase):
    def setUp(self):
        with contextlib.redirect_stdout(io.StringIO()):
            criar_banco()
            semear(forcar=True)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["INTERVALO_CONCLUSAO"] = 0
        self.cliente = self.app.test_client()

    # --- auxiliares ---------------------------------------------------------

    def consultar(self, sql, parametros=()):
        conexao = get_connection()
        linhas = conexao.execute(sql, parametros).fetchall()
        conexao.close()
        return linhas

    def token(self, caminho="/login"):
        # follow_redirects: logado, /login redireciona para a home, que também tem token.
        resposta = self.cliente.get(caminho, follow_redirects=True)
        return extrair_token(resposta.get_data(as_text=True))

    def post(self, caminho, dados=None, pagina_do_token="/login", **kwargs):
        dados = dict(dados or {})
        dados["csrf_token"] = self.token(pagina_do_token)
        return self.cliente.post(caminho, data=dados, **kwargs)

    def entrar(self, email, senha=SENHA):
        return self.post("/login", {"email": email, "senha": senha})

    def id_instrutor(self, email=INSTRUTORA):
        return self.consultar(
            "SELECT i.id FROM instrutores i JOIN usuarios u ON u.id = i.usuario_id WHERE u.email = ?",
            (email,),
        )[0]["id"]

    def dia_futuro(self, dias=7):
        return (hoje() + timedelta(days=dias)).isoformat()

    def agendar(self, instrutor_id, data, horario="09:00", veiculo_id=""):
        """Faz o fluxo completo: revisar e confirmar. Devolve a resposta final."""
        caminho_escolha = f"/instrutor/{instrutor_id}/agendar?data={data}"
        self.post(f"/instrutor/{instrutor_id}/agendar",
                  {"data": data, "horario": horario, "veiculo_id": veiculo_id},
                  pagina_do_token=caminho_escolha)
        return self.post("/agendamento/confirmar", pagina_do_token="/agendamento/confirmar")


class TestPaginasPublicas(BaseTeste):
    def test_paginas_publicas_respondem(self):
        for caminho in ("/", "/login", "/cadastro", "/offline", "/robots.txt", "/sitemap.xml", "/service-worker.js"):
            with self.subTest(caminho=caminho):
                resposta = self.cliente.get(caminho)
                self.assertEqual(resposta.status_code, 200)
                resposta.close()

    def test_entrada_mostra_numeros_reais_do_banco(self):
        html = self.cliente.get("/").get_data(as_text=True)
        total = self.consultar("SELECT COUNT(*) AS n FROM instrutores")[0]["n"]
        self.assertIn(f"<dd>{total}</dd>", html)

    def test_rota_inexistente_mostra_pagina_404_propria(self):
        resposta = self.cliente.get("/nao-existe")
        self.assertEqual(resposta.status_code, 404)
        self.assertIn("Página não encontrada", resposta.get_data(as_text=True))

    def test_rotas_privadas_exigem_login(self):
        for caminho in ("/home", "/busca", "/minhas-aulas", "/instrutor/1", "/perfil/editar"):
            with self.subTest(caminho=caminho):
                resposta = self.cliente.get(caminho)
                self.assertEqual(resposta.status_code, 302)
                self.assertIn("/login", resposta.headers["Location"])

    def test_seo_publico_e_noindex_privado(self):
        html = self.cliente.get("/").get_data(as_text=True)
        self.assertIn('content="index, follow"', html)
        self.assertIn('rel="canonical"', html)
        self.assertIn('property="og:title"', html)
        robots = self.cliente.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Disallow: /home", robots)
        self.assertIn("Sitemap:", robots)


class TestSeguranca(BaseTeste):
    def test_post_sem_token_csrf_e_recusado(self):
        resposta = self.cliente.post("/login", data={"email": CANDIDATA, "senha": SENHA})
        self.assertEqual(resposta.status_code, 302)  # volta com mensagem, sem logar
        self.assertNotIn("usuario_id", self._sessao())

    def test_cabecalhos_de_seguranca(self):
        cabecalhos = self.cliente.get("/login").headers
        self.assertIn("default-src 'self'", cabecalhos["Content-Security-Policy"])
        self.assertEqual(cabecalhos["X-Frame-Options"], "DENY")
        self.assertEqual(cabecalhos["X-Content-Type-Options"], "nosniff")
        self.assertIn("Referrer-Policy", cabecalhos)

    def test_paginas_logadas_nao_ficam_em_cache(self):
        self.entrar(CANDIDATA)
        self.assertEqual(self.cliente.get("/home").headers.get("Cache-Control"), "no-store")

    def test_templates_nao_tem_script_nem_estilo_embutido(self):
        # A CSP bloquearia, e a página quebraria em silêncio no navegador.
        for template in Path("app/templates").glob("*.html"):
            texto = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertNotRegex(texto, r'\sstyle="')
                self.assertNotRegex(texto, r"\son[a-z]+=\"")
                scripts = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>", texto)
                self.assertEqual(scripts, [])

    def test_senha_nunca_vai_para_o_cookie_no_cadastro(self):
        self.post("/cadastro", {"tipo": "candidato"}, pagina_do_token="/cadastro")
        self.post("/cadastro/dados", {
            "nome": "Teste Sonda", "email": "sonda@teste.com", "senha": "SenhaSecreta99",
            "cidade": "Vitória", "telefone": "999990000",
        }, pagina_do_token="/cadastro/dados")
        cadastro = self._sessao()["cadastro"]
        self.assertNotIn("senha", cadastro)
        self.assertTrue(cadastro["senha_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_login_errado_nao_revela_se_email_existe(self):
        existe = self.entrar(CANDIDATA, "errada").get_data(as_text=True)
        nao_existe = self.entrar("ninguem@x.com", "errada").get_data(as_text=True)
        self.assertIn("E-mail ou senha incorretos.", existe)
        self.assertIn("E-mail ou senha incorretos.", nao_existe)

    def test_redirecionamento_apos_login_so_para_o_proprio_site(self):
        resposta = self.post("/login", {"email": CANDIDATA, "senha": SENHA, "proximo": "//evil.com"})
        self.assertTrue(resposta.headers["Location"].endswith("/home"))

    def test_logout_por_get_nao_derruba_a_sessao(self):
        self.entrar(CANDIDATA)
        self.cliente.get("/logout")
        self.assertIn("usuario_id", self._sessao())
        self.post("/logout", pagina_do_token="/home")
        self.assertNotIn("usuario_id", self._sessao())

    def test_sessao_de_usuario_apagado_volta_ao_login(self):
        self.entrar(OUTRA_CANDIDATA)
        conexao = get_connection()
        conexao.execute("PRAGMA foreign_keys = OFF")
        conexao.execute("DELETE FROM usuarios WHERE email = ?", (OUTRA_CANDIDATA,))
        conexao.commit()
        conexao.close()
        resposta = self.cliente.get("/busca")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login", resposta.headers["Location"])

    def test_seed_se_recusa_a_apagar_contas_reais(self):
        conexao = get_connection()
        conexao.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES ('Real', 'real@gmail.com', 'x', 'candidato')"
        )
        conexao.commit()
        conexao.close()
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            semear()
        self.assertEqual(len(self.consultar("SELECT 1 FROM usuarios WHERE email = 'real@gmail.com'")), 1)

    def _sessao(self):
        with self.cliente.session_transaction() as sessao:
            return dict(sessao)


class TestEntradasInvalidas(BaseTeste):
    """Antes da revisão, todas estas entradas derrubavam o servidor com erro 500."""

    def setUp(self):
        super().setUp()
        self.entrar(CANDIDATA)
        self.instrutor = self.id_instrutor()

    def test_busca_com_parametros_invalidos(self):
        for consulta in ("preco_maximo=abc", "nota_minima=xyz", "ordenar=DROP", "categoria=Z", "cidade=Paris"):
            with self.subTest(consulta=consulta):
                self.assertEqual(self.cliente.get(f"/busca?{consulta}").status_code, 200)

    def test_agendamento_com_dados_invalidos(self):
        casos = [
            {"data": "lixo", "horario": "09:00"},
            {"data": self.dia_futuro(), "horario": "23:59"},
            {"data": self.dia_futuro(), "horario": "09:00", "veiculo_id": "abc"},
            {"data": self.dia_futuro(), "horario": "09:00", "veiculo_id": "99999"},
            {"data": "2020-01-01", "horario": "09:00"},
            {"data": (hoje() + timedelta(days=400)).isoformat(), "horario": "09:00"},
        ]
        for dados in casos:
            with self.subTest(dados=dados):
                resposta = self.post(f"/instrutor/{self.instrutor}/agendar", dados,
                                     pagina_do_token=f"/instrutor/{self.instrutor}/agendar")
                self.assertEqual(resposta.status_code, 302)
                self.assertNotIn("/agendamento/confirmar", resposta.headers["Location"])

    def test_veiculo_de_outro_instrutor_e_recusado(self):
        # Roberto tem um só veículo; qualquer outro do seed pertence a outra pessoa.
        self.instrutor = self.id_instrutor("roberto.almeida@habilitaplus.com")
        veiculo_alheio = self.consultar(
            """SELECT veiculo_id FROM instrutor_veiculos WHERE veiculo_id NOT IN
               (SELECT veiculo_id FROM instrutor_veiculos WHERE instrutor_id = ?) LIMIT 1""",
            (self.instrutor,),
        )[0]["veiculo_id"]
        resposta = self.post(f"/instrutor/{self.instrutor}/agendar",
                             {"data": self.dia_futuro(), "horario": "09:00", "veiculo_id": veiculo_alheio},
                             pagina_do_token=f"/instrutor/{self.instrutor}/agendar")
        self.assertNotIn("/agendamento/confirmar", resposta.headers["Location"])

    def test_instrutor_inexistente(self):
        self.assertEqual(self.cliente.get("/instrutor/9999").status_code, 404)
        resposta = self.post("/instrutor/9999/agendar", {"data": self.dia_futuro(), "horario": "09:00"})
        self.assertIn("/busca", resposta.headers["Location"])

    def test_calendario_com_parametros_invalidos(self):
        for consulta in ("data=lixo", "mes=13-2026", "mes=abc", "data=2020-01-01"):
            with self.subTest(consulta=consulta):
                self.assertEqual(self.cliente.get(f"/instrutor/{self.instrutor}/agendar?{consulta}").status_code, 200)


class TestFluxoDeAgendamento(BaseTeste):
    def setUp(self):
        super().setUp()
        self.instrutor = self.id_instrutor()

    def test_agendamento_completo_grava_valores_congelados(self):
        self.entrar(CANDIDATA)
        veiculo = self.consultar(
            "SELECT v.id, v.valor_locacao FROM veiculos v JOIN instrutor_veiculos iv ON iv.veiculo_id = v.id WHERE iv.instrutor_id = ? LIMIT 1",
            (self.instrutor,),
        )[0]
        resposta = self.agendar(self.instrutor, self.dia_futuro(), "10:00", veiculo["id"])
        self.assertIn("/sucesso", resposta.headers["Location"])

        aula = self.consultar("SELECT * FROM agendamentos ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(aula["status"], "agendado")
        self.assertEqual(aula["valor_locacao"], veiculo["valor_locacao"])

        sucesso = self.cliente.get(resposta.headers["Location"]).get_data(as_text=True)
        self.assertIn("Aula agendada", sucesso)
        self.assertNotIn("e-mail", sucesso)  # a promessa falsa de envio por e-mail saiu

    def test_mesmo_horario_nao_pode_ser_reservado_duas_vezes(self):
        data = self.dia_futuro()
        self.entrar(CANDIDATA)
        self.assertIn("/sucesso", self.agendar(self.instrutor, data, "11:00").headers["Location"])

        self.post("/logout", pagina_do_token="/home")
        self.entrar(OUTRA_CANDIDATA)
        segunda = self.agendar(self.instrutor, data, "11:00")
        self.assertNotIn("/sucesso", segunda.headers["Location"])
        ativas = self.consultar(
            "SELECT COUNT(*) AS n FROM agendamentos WHERE instrutor_id = ? AND data = ? AND horario = '11:00' AND status = 'agendado'",
            (self.instrutor, data),
        )[0]["n"]
        self.assertEqual(ativas, 1)

    def test_indice_parcial_do_banco_barra_duplicidade_mesmo_sem_a_aplicacao(self):
        conexao = get_connection()
        valores = (self.instrutor, self.dia_futuro(), "15:00")
        conexao.execute(
            "INSERT INTO agendamentos (candidato_id, instrutor_id, data, horario, valor) VALUES (5, ?, ?, ?, 90)", valores
        )
        with self.assertRaises(Exception):
            conexao.execute(
                "INSERT INTO agendamentos (candidato_id, instrutor_id, data, horario, valor) VALUES (6, ?, ?, ?, 90)", valores
            )
        conexao.close()

    def test_candidato_nao_marca_duas_aulas_no_mesmo_horario(self):
        data = self.dia_futuro()
        self.entrar(CANDIDATA)
        self.agendar(self.instrutor, data, "13:00")
        outro = self.id_instrutor("fernanda.souza@habilitaplus.com")
        resposta = self.agendar(outro, data, "13:00")
        self.assertNotIn("/sucesso", resposta.headers["Location"])

    def test_cancelar_libera_o_horario(self):
        data = self.dia_futuro()
        self.entrar(CANDIDATA)
        self.agendar(self.instrutor, data, "14:00")
        aula_id = self.consultar("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["id"]

        self.post(f"/agendamento/{aula_id}/cancelar", pagina_do_token="/minhas-aulas")
        self.assertEqual(self.consultar("SELECT status FROM agendamentos WHERE id = ?", (aula_id,))[0]["status"], "cancelado")
        self.assertIn("/sucesso", self.agendar(self.instrutor, data, "14:00").headers["Location"])

    def test_nao_cancela_aula_de_outra_pessoa(self):
        self.entrar(CANDIDATA)
        self.agendar(self.instrutor, self.dia_futuro(), "16:00")
        aula_id = self.consultar("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["id"]
        self.post("/logout", pagina_do_token="/home")

        self.entrar(OUTRA_CANDIDATA)
        resposta = self.post(f"/agendamento/{aula_id}/cancelar", pagina_do_token="/minhas-aulas")
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(self.consultar("SELECT status FROM agendamentos WHERE id = ?", (aula_id,))[0]["status"], "agendado")

    def test_instrutor_confirma_aula(self):
        self.entrar(CANDIDATA)
        self.agendar(self.instrutor, self.dia_futuro(), "08:00")
        aula_id = self.consultar("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["id"]
        self.post("/logout", pagina_do_token="/home")

        self.entrar(INSTRUTORA)
        self.assertIn("Confirmar", self.cliente.get("/home").get_data(as_text=True))
        self.post(f"/agendamento/{aula_id}/aceitar", pagina_do_token="/minhas-aulas")
        self.assertEqual(self.consultar("SELECT status FROM agendamentos WHERE id = ?", (aula_id,))[0]["status"], "confirmado")

    def test_instrutor_nao_pode_agendar(self):
        self.entrar(INSTRUTORA)
        resposta = self.cliente.get(f"/instrutor/{self.instrutor}/agendar")
        self.assertEqual(resposta.status_code, 302)
        perfil = self.cliente.get(f"/instrutor/{self.instrutor}").get_data(as_text=True)
        self.assertNotIn("Agendar aula", perfil)
        self.assertIn("Editar meu perfil", perfil)


class TestCicloDeVidaDasAulas(BaseTeste):
    def test_aula_que_ja_aconteceu_vira_concluida_e_pode_ser_avaliada(self):
        """Antes, nada mudava o status para 'concluido': aulas reais nunca eram avaliáveis."""
        instrutor = self.id_instrutor()
        candidata = self.consultar("SELECT id FROM usuarios WHERE email = ?", (CANDIDATA,))[0]["id"]
        ontem = (hoje() - timedelta(days=1)).isoformat()
        conexao = get_connection()
        cursor = conexao.execute(
            "INSERT INTO agendamentos (candidato_id, instrutor_id, data, horario, status, valor) VALUES (?, ?, ?, '10:00', 'agendado', 90)",
            (candidata, instrutor, ontem),
        )
        aula_id = cursor.lastrowid
        conexao.commit()
        conexao.close()

        self.entrar(CANDIDATA)
        self.assertIn("Avaliar aula", self.cliente.get("/minhas-aulas").get_data(as_text=True))
        self.assertEqual(self.consultar("SELECT status FROM agendamentos WHERE id = ?", (aula_id,))[0]["status"], "concluido")

        resposta = self.post(f"/agendamento/{aula_id}/avaliar", {"nota": "5", "comentario": "Ótima"},
                             pagina_do_token=f"/agendamento/{aula_id}/avaliar")
        self.assertIn(f"/instrutor/{instrutor}", resposta.headers["Location"])
        self.assertEqual(len(self.consultar("SELECT 1 FROM avaliacoes WHERE agendamento_id = ?", (aula_id,))), 1)

        segunda = self.post(f"/agendamento/{aula_id}/avaliar", {"nota": "1"}, pagina_do_token="/minhas-aulas")
        self.assertEqual(segunda.status_code, 302)
        self.assertEqual(len(self.consultar("SELECT 1 FROM avaliacoes WHERE agendamento_id = ?", (aula_id,))), 1)

    def test_aula_futura_nao_pode_ser_avaliada(self):
        self.entrar(CANDIDATA)
        instrutor = self.id_instrutor()
        self.agendar(instrutor, self.dia_futuro(), "09:00")
        aula_id = self.consultar("SELECT id FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["id"]
        resposta = self.cliente.get(f"/agendamento/{aula_id}/avaliar")
        self.assertEqual(resposta.status_code, 302)

    def test_horario_de_hoje_que_ja_passou_nao_pode_ser_marcado(self):
        if agora().hour < 8:
            self.skipTest("Antes das 8h ainda não há horário passado hoje.")
        self.entrar(CANDIDATA)
        instrutor = self.id_instrutor()
        resposta = self.post(f"/instrutor/{instrutor}/agendar", {"data": hoje().isoformat(), "horario": "07:00"},
                             pagina_do_token=f"/instrutor/{instrutor}/agendar")
        self.assertNotIn("/agendamento/confirmar", resposta.headers["Location"])


class TestCadastroEPerfil(BaseTeste):
    def test_cadastro_completo_de_candidato_entra_logado(self):
        self.post("/cadastro", {"tipo": "candidato"}, pagina_do_token="/cadastro")
        self.post("/cadastro/dados", {"nome": "Bruna Lima", "email": "bruna@teste.com", "senha": "senhaforte1",
                                      "cidade": "Serra", "telefone": "98888-7777"}, pagina_do_token="/cadastro/dados")
        self.post("/cadastro/categoria", {"categorias": ["A", "B"]}, pagina_do_token="/cadastro/categoria")
        self.post("/cadastro/preferencias", {"prefere_instrutoras_mulheres": "on"}, pagina_do_token="/cadastro/preferencias")
        resposta = self.post("/cadastro/acessibilidade", {"tipo_deficiencia": "", "canal_comunicacao": "libras"},
                             pagina_do_token="/cadastro/acessibilidade")
        self.assertTrue(resposta.headers["Location"].endswith("/home"))

        usuario = self.consultar("SELECT id, telefone FROM usuarios WHERE email = 'bruna@teste.com'")[0]
        self.assertEqual(usuario["telefone"], "27988887777")
        categorias = [l["categoria"] for l in self.consultar(
            "SELECT categoria FROM candidato_categorias WHERE usuario_id = ? ORDER BY categoria", (usuario["id"],))]
        self.assertEqual(categorias, ["A", "B"])
        # Escolher Libras sem informar deficiência antes fazia a preferência sumir.
        perfil = self.consultar("SELECT canal_comunicacao FROM perfis_acessibilidade WHERE usuario_id = ?", (usuario["id"],))
        self.assertEqual(perfil[0]["canal_comunicacao"], "libras")

        busca = self.cliente.get("/busca").get_data(as_text=True)
        self.assertIn("Aplicamos as preferências do seu cadastro", busca)

    def test_validacoes_do_cadastro(self):
        self.post("/cadastro", {"tipo": "candidato"}, pagina_do_token="/cadastro")
        base = {"nome": "Bruna Lima", "email": "bruna@teste.com", "senha": "senhaforte1", "cidade": "Serra", "telefone": ""}
        for campo, valor in (("email", "sem-arroba"), ("senha", "curta"), ("cidade", "Paris"),
                             ("telefone", "123"), ("email", CANDIDATA), ("nome", "A")):
            with self.subTest(campo=campo, valor=valor):
                dados = dict(base, **{campo: valor})
                resposta = self.post("/cadastro/dados", dados, pagina_do_token="/cadastro/dados")
                self.assertEqual(resposta.status_code, 400)

    def test_instrutor_edita_perfil_e_aulas_antigas_mantem_preco(self):
        self.entrar(CANDIDATA)
        instrutor = self.id_instrutor()
        self.agendar(instrutor, self.dia_futuro(), "17:00")
        valor_antigo = self.consultar("SELECT valor FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["valor"]
        self.post("/logout", pagina_do_token="/home")

        self.entrar(INSTRUTORA)
        resposta = self.post("/perfil/editar", {"valor_aula": "150,00", "categorias_cnh": ["B", "C"],
                                                 "regiao_atuacao": "Vitória", "atende_libras": "on"},
                             pagina_do_token="/perfil/editar")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.consultar("SELECT valor_aula FROM instrutores WHERE id = ?", (instrutor,))[0]["valor_aula"], 150)
        categorias = [l["categoria"] for l in self.consultar(
            "SELECT categoria FROM instrutor_categorias WHERE instrutor_id = ? ORDER BY categoria", (instrutor,))]
        self.assertEqual(categorias, ["B", "C"])
        self.assertEqual(self.consultar("SELECT valor FROM agendamentos ORDER BY id DESC LIMIT 1")[0]["valor"], valor_antigo)

    def test_candidato_nao_acessa_edicao_de_perfil(self):
        self.entrar(CANDIDATA)
        self.assertEqual(self.cliente.get("/perfil/editar").status_code, 302)


class TestBusca(BaseTeste):
    def setUp(self):
        super().setUp()
        self.entrar(CANDIDATA)

    def nomes(self, consulta):
        html = self.cliente.get(f"/busca?ordenar=avaliacao&{consulta}").get_data(as_text=True)
        return set(re.findall(r'class="link-cartao"[^>]*>([^<]+)</a>', html))

    def test_filtro_por_categoria_usa_a_tabela_de_juncao(self):
        esperado = {linha["nome"] for linha in self.consultar(
            """SELECT u.nome FROM instrutores i JOIN usuarios u ON u.id = i.usuario_id
               WHERE EXISTS (SELECT 1 FROM instrutor_categorias ic WHERE ic.instrutor_id = i.id AND ic.categoria = 'A')""")}
        self.assertEqual(self.nomes("categoria=A"), esperado)

    def test_busca_por_nome(self):
        self.assertEqual(self.nomes("q=Juliana"), {"Juliana Oliveira"})

    def test_busca_por_texto_malicioso_e_tratada_como_texto(self):
        resposta = self.cliente.get("/busca?q=%27%3B DROP TABLE usuarios;--")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(self.consultar("SELECT COUNT(*) AS n FROM usuarios")[0]["n"] > 0)


if __name__ == "__main__":
    unittest.main()
