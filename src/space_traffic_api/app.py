from __future__ import annotations

import atexit

from flask import Flask

from .api import create_api_blueprint
from .config import AppConfig
from .seed_data import build_ships, build_stations
from .simulation import SimulationService
from .store import SQLiteStore


def create_app() -> Flask:
    config = AppConfig.from_env()
    store = SQLiteStore(config.db_path)
    store.init_schema()

    stations = build_stations(catalog_path=config.seed_catalog_path)
    ships = build_ships(stations=stations, catalog_path=config.seed_catalog_path)

    store.seed_stations(stations)
    store.seed_ships(ships)
    store.seed_ship_states(ships)

    simulation = SimulationService(config=config, store=store, stations=stations, ships=ships)
    if not config.disable_generator:
        simulation.start()

    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint(
            api_key=config.api_key,
            store=store,
            simulation=simulation,
        )
    )

    app.config["space_store"] = store
    app.config["space_simulation"] = simulation

    def _cleanup() -> None:
        simulation.stop(timeout=65.0)
        store.close()

    atexit.register(_cleanup)

    return app
