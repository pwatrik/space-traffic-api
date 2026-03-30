from __future__ import annotations

import atexit

from flask import Flask

from .config import AppConfig
from .generator import DepartureGenerator
from .routes import create_api_blueprint
from .runtime import RuntimeState
from .seed_data import build_ships, build_stations
from .store import SQLiteStore


def create_app() -> Flask:
    config = AppConfig.from_env()
    store = SQLiteStore(config.db_path)
    store.init_schema()

    stations = build_stations()
    ships = build_ships(stations=stations, count=220, seed=9001)

    store.seed_stations(stations)
    store.seed_ships(ships)

    runtime = RuntimeState(config=config, store=store)
    generator = DepartureGenerator(store=store, runtime=runtime, stations=stations, ships=ships)
    if not config.disable_generator:
        generator.start()

    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint(
            api_key=config.api_key,
            store=store,
            runtime=runtime,
            generator=generator,
        )
    )

    app.config["space_runtime"] = runtime
    app.config["space_store"] = store
    app.config["space_generator"] = generator

    def _cleanup() -> None:
        if generator.is_alive():
            generator.stop()
            generator.join(timeout=2.0)
        store.close()

    atexit.register(_cleanup)

    return app
