from pathlib import Path

import click
from flask import Flask, jsonify, render_template
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import ENV_PATH, Config
from .extensions import csrf, db, login_manager, migrate
from .utils import kes, valid_email


def create_app(config_overrides=None):
    # Static files live in public/static so that Vercel can serve them from its CDN.
    static_dir = Path(__file__).resolve().parent.parent / "public" / "static"
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    if app.config["APP_ENV"] == "production" and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("Set a strong SECRET_KEY before running in production.")

    if not app.config["GEOAPIFY_API_KEY"] and not app.testing:
        click.echo(f"[Express Mtaani] GEOAPIFY_API_KEY is empty, so maps are off. Looked for: {ENV_PATH} "
                   f"(file exists: {ENV_PATH.exists()})", err=True)

    if app.config["APP_ENV"] == "production":
        # Behind Vercel's proxy: trust its headers so we see the real client IP and https.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401  (register models with SQLAlchemy)
    from .admin import bp as admin_bp
    from .api import bp as api_bp
    from .auth import bp as auth_bp
    from .rider import bp as rider_bp
    from .storefront import bp as shop_bp

    for blueprint in (shop_bp, auth_bp, rider_bp, admin_bp, api_bp):
        app.register_blueprint(blueprint)

    app.jinja_env.filters["kes"] = kes

    @app.context_processor
    def inject_maps():
        return {"geo_key": app.config["GEOAPIFY_API_KEY"]}

    @app.get("/healthz")
    def healthz():
        """For uptime monitors: 200 when the site and its database are working."""
        try:
            db.session.execute(text("SELECT 1 FROM users LIMIT 1"))  # also proves the tables exist
            return jsonify(status="ok"), 200
        except Exception:  # noqa: BLE001  (any database failure means unhealthy)
            return jsonify(status="database unavailable or tables missing (run init-db)"), 503

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403, message="You do not have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, message="We could not find that page."), 404

    # ---- Command line helpers ----

    @app.cli.command("init-db")
    def init_db():
        """Create all tables (quick start). Use `flask db migrate` once you manage schema changes."""
        db.create_all()
        click.echo(f"Database tables created on {db.engine.dialect.name}.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True, default="Admin")
    @click.option("--phone", prompt=True, default="0700000000")
    @click.password_option()
    def create_admin(email, name, phone, password):
        """Create an administrator account."""
        from .models import User
        from .utils import normalize_phone

        email = email.strip().lower()
        if not valid_email(email):
            raise click.ClickException("That email address does not look valid.")
        if len(password) < 10:
            raise click.ClickException("Use a password of at least 10 characters for an admin.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("An account with that email already exists.")
        user = User(name=name.strip(), email=email, phone=normalize_phone(phone) or "+254700000000",
                    role="admin", approved=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin {email} created on {db.engine.dialect.name}. Sign in at /login.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add three demo shops with sample products (demo prices)."""
        from .seed import seed
        click.echo(seed())

    return app
