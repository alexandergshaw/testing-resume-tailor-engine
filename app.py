from flask import Flask

from tailor.web.api import api
from tailor.web.routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.register_blueprint(bp)
    app.register_blueprint(api)
    return app


# WSGI entry point (also what Vercel's Python runtime picks up via api/index.py).
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
