from __future__ import annotations

import atexit

from flask import Flask

from .api import create_api_blueprint
from .config import AppConfig
from .seed_data import build_ships, build_stations, load_seed_catalog
from .simulation import SimulationService
from .simulation.runtime import _parse_deterministic_start
from .store import SQLiteStore


def create_app() -> Flask:
    config = AppConfig.from_env()
    store = SQLiteStore(config.db_path)
    store.init_schema()

    catalog = load_seed_catalog(config.seed_catalog_path)
    stations = build_stations(catalog_path=config.seed_catalog_path, catalog=catalog)
    ships = build_ships(stations=stations, catalog_path=config.seed_catalog_path, catalog=catalog)

    sim_epoch = _parse_deterministic_start(config.deterministic_start_time).isoformat()

    store.seed_stations(stations)
    store.seed_ships(ships)
    store.seed_ship_states(ships, now_iso=sim_epoch)

    simulation = SimulationService(config=config, store=store, stations=stations, ships=ships, catalog=catalog)
    if not config.disable_generator:
        simulation.start()

    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint(
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
