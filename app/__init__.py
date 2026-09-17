import os
import secrets

from flask import Flask


def create_app():
    app = Flask(__name__)

    # Sem a variável de ambiente, gera uma chave aleatória a cada início: as sessões
    # não sobrevivem a um restart, mas nunca ficam previsíveis (o que permitiria
    # forjar o cookie de login de qualquer usuário).
    app.config["SECRET_KEY"] = os.environ.get("HABILITA_SECRET_KEY") or secrets.token_hex(32)

    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.busca import busca_bp
    from app.routes.instrutores import instrutores_bp
    from app.routes.agendamentos import agendamentos_bp
    from app.routes.avaliacoes import avaliacoes_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(busca_bp)
    app.register_blueprint(instrutores_bp)
    app.register_blueprint(agendamentos_bp)
    app.register_blueprint(avaliacoes_bp)

    return app
