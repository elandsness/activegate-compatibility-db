"""Route blueprints for the ActiveGate Compatibility API."""

from flask import Blueprint

# All route modules import their own shared components (helpers.py)
# to avoid circular imports. The factory in __init__.py wires them together.


def register_blueprints(app) -> None:
    """Register all route blueprints on the Flask app."""
    from src.api.routes.health import health_bp
    from src.api.routes.compatibility import compatibility_bp
    from src.api.routes.data import data_bp
    from src.api.routes.batch import batch_bp
    from src.api.routes.ingestion import ingestion_bp
    from src.api.routes.admin import admin_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(compatibility_bp, url_prefix="/api")
    app.register_blueprint(data_bp, url_prefix="/api")
    app.register_blueprint(batch_bp, url_prefix="/api")
    app.register_blueprint(ingestion_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
