import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # host=0.0.0.0 expõe o servidor na rede local (para testar no celular).
    # NUNCA use debug=True com host público: o debugger do Werkzeug permite
    # execução de código arbitrário na máquina.
    host = os.environ.get("HABILITA_HOST", "127.0.0.1")
    debug = host == "127.0.0.1"
    app.run(host=host, port=5000, debug=debug)
