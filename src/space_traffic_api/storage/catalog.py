from __future__ import annotations

import json
import random
from typing import Any

from .shared import StorageContext


class CatalogRepository:
    def __init__(self, context: StorageContext):
        self._context = context

    def seed_stations(self, stations: list[dict[str, Any]]) -> None:
        rows = []
        for station in stations:
            row = dict(station)
            row["allowed_size_classes"] = json.dumps(station.get("allowed_size_classes", []))
            row["economy_profile"] = json.dumps(station.get("economy_profile", {}))
            row["economy_state"] = json.dumps(station.get("economy_state", {}))
            rows.append(row)

        with self._context.lock:
            self._context.conn.executemany(
                """
                INSERT INTO stations (
                    id,
                    name,
                    body_name,
                    body_type,
                    parent_body,
                    cargo_type,
                    allowed_size_classes,
                    economy_profile,
                    economy_state
                )
                VALUES (
                    :id,
                    :name,
                    :body_name,
                    :body_type,
                    :parent_body,
                    :cargo_type,
                    :allowed_size_classes,
                    :economy_profile,
                    :economy_state
                )
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    body_name=excluded.body_name,
                    body_type=excluded.body_type,
                    parent_body=excluded.parent_body,
                    cargo_type=excluded.cargo_type,
                    allowed_size_classes=excluded.allowed_size_classes,
                    economy_profile=excluded.economy_profile,
                    economy_state=excluded.economy_state
                """,
                rows,
            )
            self._context.conn.commit()

    def set_ship_cargo(self, ship_id: str, cargo: str) -> bool:
        with self._context.lock:
            cur = self._context.conn.execute(
                "UPDATE ships SET cargo = ? WHERE id = ?",
                (cargo, ship_id),
            )
            self._context.conn.commit()
            return int(cur.rowcount) > 0

    def seed_ships(self, ships: list[dict[str, Any]]) -> None:
        with self._context.lock:
            self._context.conn.executemany(
                """
                INSERT INTO ships (
                    id, name, faction, ship_type, size_class, displacement_million_m3, home_station_id,
                    captain_name, cargo, crew, passengers
                )
                VALUES (
                    :id, :name, :faction, :ship_type, :size_class, :displacement_million_m3, :home_station_id,
                    :captain_name, :cargo, :crew, :passengers
                )
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    faction=excluded.faction,
                    ship_type=excluded.ship_type,
                    size_class=excluded.size_class,
                    displacement_million_m3=excluded.displacement_million_m3,
                    home_station_id=excluded.home_station_id,
                    captain_name=excluded.captain_name,
                    cargo=excluded.cargo,
                    crew=excluded.crew,
                    passengers=excluded.passengers
                """,
                ships,
            )
            self._context.conn.commit()

    def list_stations(
        self,
        body_type: str | None = None,
        offset: int = 0,
        limit: int = 1000,
        order_by: str = "body_type",
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        """List stations with pagination. Returns (rows, total_count)."""
        # Validate order_by and order to prevent SQL injection
        valid_order_by = {"id", "name", "body_name", "body_type", "parent_body"}
        valid_order = {"asc", "desc"}
        order_by = order_by if order_by in valid_order_by else "body_type"
        order = order if order in valid_order else "asc"

        where_clauses: list[str] = []
        params: list[Any] = []
        if body_type:
            where_clauses.append("body_type = ?")
            params.append(body_type)

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM stations{where_sql}"
        with self._context.lock:
            total_count = int(self._context.conn.execute(count_query, params).fetchone()[0])
            # Get paginated results
            query = f"SELECT * FROM stations{where_sql} ORDER BY {order_by} {order}, id ASC LIMIT ? OFFSET ?"
            rows = self._context.conn.execute(query, params + [limit, offset]).fetchall()

        records = [dict(row) for row in rows]
        for row in records:
            raw = row.get("allowed_size_classes")
            try:
                row["allowed_size_classes"] = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                row["allowed_size_classes"] = []

            raw_profile = row.get("economy_profile")
            try:
                row["economy_profile"] = json.loads(raw_profile) if raw_profile else {}
            except json.JSONDecodeError:
                row["economy_profile"] = {}

            raw_state = row.get("economy_state")
            try:
                row["economy_state"] = json.loads(raw_state) if raw_state else {}
            except json.JSONDecodeError:
                row["economy_state"] = {}

            row["economy_derived"] = self._derive_station_economy(row)
        return records, total_count

    def _derive_station_economy(self, station: dict[str, Any]) -> dict[str, float]:
        profile = station.get("economy_profile") if isinstance(station.get("economy_profile"), dict) else {}
        state = station.get("economy_state") if isinstance(station.get("economy_state"), dict) else {}

        supply = float(state.get("supply_index", 1.0) or 1.0)
        demand = float(state.get("demand_index", 1.0) or 1.0)
        price = float(state.get("price_index", 1.0) or 1.0)
        fuel = float(state.get("fuel_price_index", 1.0) or 1.0)
        material_demand = float(profile.get("manufacturing_material_demand", 0.5) or 0.5)

        distance_rank = float(profile.get("distance_rank", 5) or 5)
        normalized_dist = (distance_rank - 1.0) / 9.0  # [0.0 Mercury … 1.0 Pluto]

        safe_supply = max(0.01, supply)
        local_value_score = (demand / safe_supply) * price
        scarcity_index = demand / safe_supply
        fuel_pressure_score = fuel * (1.0 + material_demand * 0.15 + normalized_dist * 0.5)

        return {
            "local_value_score": round(max(0.1, min(10.0, local_value_score)), 3),
            "scarcity_index": round(max(0.1, min(10.0, scarcity_index)), 3),
            "fuel_pressure_score": round(max(0.1, min(10.0, fuel_pressure_score)), 3),
        }

    def list_ships(
        self,
        faction: str | None = None,
        home_station_id: str | None = None,
        cargo: str | None = None,
        ship_type: str | None = None,
        offset: int = 0,
        limit: int = 1000,
        order_by: str = "id",
        order: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        """List ships with pagination. Returns (rows, total_count)."""
        # Validate order_by and order to prevent SQL injection
        valid_order_by = {"id", "name", "faction", "ship_type", "cargo", "home_station_id", "size_class"}
        valid_order = {"asc", "desc"}
        order_by = order_by if order_by in valid_order_by else "id"
        order = order if order in valid_order else "asc"

        where_clauses: list[str] = []
        params: list[Any] = []
        if faction:
            where_clauses.append("faction = ?")
            params.append(faction)
        if home_station_id:
            where_clauses.append("home_station_id = ?")
            params.append(home_station_id)
        if cargo:
            where_clauses.append("cargo = ?")
            params.append(cargo)
        if ship_type:
            where_clauses.append("ship_type = ?")
            params.append(ship_type)

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM ships{where_sql}"
        with self._context.lock:
            total_count = int(self._context.conn.execute(count_query, params).fetchone()[0])
            # Get paginated results
            if order_by == "id":
                order_clause = "ORDER BY id " + order
            else:
                # Add a unique tie-breaker to ensure stable pagination when order_by has ties
                order_clause = f"ORDER BY {order_by} {order}, id ASC"
            query = f"SELECT * FROM ships{where_sql} {order_clause} LIMIT ? OFFSET ?"
            rows = self._context.conn.execute(query, params + [limit, offset]).fetchall()
        return [dict(row) for row in rows], total_count

    def count_stations(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])

    def count_ships(self) -> int:
        with self._context.lock:
            return int(self._context.conn.execute("SELECT COUNT(*) FROM ships").fetchone()[0])

    def advance_station_economy(
        self,
        elapsed_days: float,
        rng: random.Random | None = None,
        magnitude: float = 1.0,
    ) -> int:
        if elapsed_days <= 0:
            return 0

        rng = rng or random.Random()
        magnitude = max(0.1, min(5.0, float(magnitude)))
        # producer_rate/consumer_rate are per-day rates; elapsed_days keeps the
        # drift proportional to simulated time elapsed.
        day_factor = max(1.0 / 1440.0, elapsed_days)

        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT id, economy_profile, economy_state FROM stations"
            ).fetchall()

            updates: list[tuple[str, str]] = []
            for row in rows:
                station_id = str(row["id"])

                try:
                    profile = json.loads(row["economy_profile"]) if row["economy_profile"] else {}
                except json.JSONDecodeError:
                    profile = {}

                try:
                    state = json.loads(row["economy_state"]) if row["economy_state"] else {}
                except json.JSONDecodeError:
                    state = {}

                producer_rate = float(profile.get("producer_rate", 0.06) or 0.06)
                consumer_rate = float(profile.get("consumer_rate", 0.06) or 0.06)

                supply_index = float(state.get("supply_index", 1.0) or 1.0)
                demand_index = float(state.get("demand_index", 1.0) or 1.0)
                price_index = float(state.get("price_index", 1.0) or 1.0)

                noise_supply = (rng.random() - 0.5) * 0.01
                noise_demand = (rng.random() - 0.5) * 0.01

                supply_delta = (((producer_rate * 1.1) - (consumer_rate * 0.8)) * day_factor + noise_supply) * magnitude
                scarcity_pressure = max(0.0, 1.0 - supply_index)
                demand_delta = (((consumer_rate * 1.0) - (producer_rate * 0.3)) * day_factor) * magnitude
                demand_delta += scarcity_pressure * 0.02 * day_factor
                demand_delta += noise_demand

                # Price converges toward demand/supply equilibrium: if demand
                # exceeds supply price rises slowly and vice-versa.
                safe_supply = max(0.01, supply_index)
                target_price = demand_index / safe_supply
                price_delta = (target_price - price_index) * 0.05 * day_factor * magnitude

                state["supply_index"] = round(max(0.1, min(5.0, supply_index + supply_delta)), 4)
                state["demand_index"] = round(max(0.1, min(5.0, demand_index + demand_delta)), 4)
                state["price_index"] = round(max(0.5, min(3.0, price_index + price_delta)), 4)

                updates.append((json.dumps(state), station_id))

            if updates:
                self._context.conn.executemany(
                    "UPDATE stations SET economy_state = ? WHERE id = ?",
                    updates,
                )
                self._context.conn.commit()

            return len(updates)

    def apply_departure_economy_impact(
        self,
        source_station_id: str,
        destination_station_id: str,
        rng: random.Random | None = None,
        magnitude: float = 0.012,
    ) -> int:
        if not source_station_id or not destination_station_id:
            return 0

        rng = rng or random.Random()
        magnitude = max(0.001, min(0.2, float(magnitude)))

        with self._context.lock:
            ids = [source_station_id]
            if destination_station_id != source_station_id:
                ids.append(destination_station_id)

            placeholders = ",".join("?" for _ in ids)
            rows = self._context.conn.execute(
                f"SELECT id, economy_state FROM stations WHERE id IN ({placeholders})",
                ids,
            ).fetchall()

            if not rows:
                return 0

            by_id = {str(row["id"]): row for row in rows}
            updates: list[tuple[str, str]] = []

            src_row = by_id.get(source_station_id)
            if src_row:
                try:
                    src_state = json.loads(src_row["economy_state"]) if src_row["economy_state"] else {}
                except json.JSONDecodeError:
                    src_state = {}

                src_supply = float(src_state.get("supply_index", 1.0) or 1.0)
                supply_drop = magnitude * (0.8 + (rng.random() * 0.4))
                src_state["supply_index"] = round(max(0.1, min(5.0, src_supply - supply_drop)), 4)
                updates.append((json.dumps(src_state), source_station_id))

            dst_row = by_id.get(destination_station_id)
            if dst_row:
                try:
                    dst_state = json.loads(dst_row["economy_state"]) if dst_row["economy_state"] else {}
                except json.JSONDecodeError:
                    dst_state = {}

                dst_demand = float(dst_state.get("demand_index", 1.0) or 1.0)
                demand_relief = magnitude * (0.6 + (rng.random() * 0.4))
                dst_state["demand_index"] = round(max(0.1, min(5.0, dst_demand - demand_relief)), 4)

                # Arriving cargo eases destination price pressure — a shipment heading
                # there signals incoming supply, nudging price slightly downward.
                dst_price = float(dst_state.get("price_index", 1.0) or 1.0)
                price_ease = magnitude * 0.3 * (0.8 + (rng.random() * 0.4))
                dst_state["price_index"] = round(max(0.5, min(3.0, dst_price - price_ease)), 4)

                updates.append((json.dumps(dst_state), destination_station_id))

            if updates:
                self._context.conn.executemany(
                    "UPDATE stations SET economy_state = ? WHERE id = ?",
                    updates,
                )
                self._context.conn.commit()

            return len(updates)

    def get_economy_summary(self) -> dict[str, Any]:
        """Return aggregate price/supply/demand stats across all stations."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT economy_state FROM stations"
            ).fetchall()

        prices: list[float] = []
        supplies: list[float] = []
        demands: list[float] = []
        for row in rows:
            try:
                state = json.loads(row["economy_state"]) if row["economy_state"] else {}
            except json.JSONDecodeError:
                state = {}
            prices.append(float(state.get("price_index", 1.0) or 1.0))
            supplies.append(float(state.get("supply_index", 1.0) or 1.0))
            demands.append(float(state.get("demand_index", 1.0) or 1.0))

        n = len(prices)
        if n == 0:
            return {"station_count": 0}

        return {
            "station_count": n,
            "price_index_avg": round(sum(prices) / n, 3),
            "price_index_min": round(min(prices), 3),
            "price_index_max": round(max(prices), 3),
            "supply_index_avg": round(sum(supplies) / n, 3),
            "demand_index_avg": round(sum(demands) / n, 3),
            "stations_above_equilibrium": sum(1 for p in prices if p > 1.0),
            "stations_below_equilibrium": sum(1 for p in prices if p < 1.0),
        }

    def get_ship_stats_by_faction(self) -> dict[str, int]:
        """Return ship count grouped by faction."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT faction, COUNT(*) as count FROM ships GROUP BY faction ORDER BY faction"
            ).fetchall()
        return {row["faction"]: row["count"] for row in rows}

    def get_ship_stats_by_type(self) -> dict[str, int]:
        """Return ship count grouped by ship_type."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT ship_type, COUNT(*) as count FROM ships GROUP BY ship_type ORDER BY ship_type"
            ).fetchall()
        return {row["ship_type"]: row["count"] for row in rows}

    def get_cargo_stats(self) -> dict[str, int]:
        """Return ship count grouped by cargo type."""
        with self._context.lock:
            rows = self._context.conn.execute(
                "SELECT cargo, COUNT(*) as count FROM ships WHERE cargo <> '' GROUP BY cargo ORDER BY cargo"
            ).fetchall()
        return {row["cargo"]: row["count"] for row in rows}
