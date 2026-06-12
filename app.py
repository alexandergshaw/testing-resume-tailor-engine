from flask import Flask

from tailor.web.routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    # Local single-user tool; the secret key only signs flash-message cookies.
    app.secret_key = "resume-tailor-local"
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
