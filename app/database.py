import json
import time

from .config import MYSQL_CONFIG


class TrafficDatabase:
    def __init__(self):
        self.enabled = all(
            MYSQL_CONFIG.get(key) for key in ("host", "user", "password", "database")
        )
        self.available = False
        self.error = None
        if self.enabled:
            self.initialize()

    def connect(self):
        import mysql.connector

        return mysql.connector.connect(**MYSQL_CONFIG)

    def initialize(self):
        try:
            with self.connect() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS traffic_snapshots (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        total_vehicles INT NOT NULL,
                        traffic_density VARCHAR(16) NOT NULL,
                        green_lane VARCHAR(16) NOT NULL,
                        green_time INT NOT NULL,
                        final_signal VARCHAR(16) NOT NULL,
                        lane_counts JSON NOT NULL,
                        queue_metrics JSON NOT NULL,
                        vehicle_types JSON NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS signal_events (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        event_type VARCHAR(32) NOT NULL,
                        lane_name VARCHAR(16),
                        signal_status VARCHAR(16) NOT NULL,
                        green_time INT NOT NULL,
                        traffic_density VARCHAR(16) NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS emergency_events (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        event_type VARCHAR(32) NOT NULL,
                        lane_name VARCHAR(16),
                        details JSON
                    )
                    """
                )
                db.commit()
            self.available = True
            self.error = None
        except Exception as exc:
            self.available = False
            self.error = str(exc)

    def log_snapshot(self, state):
        if not self.available:
            return

        try:
            with self.connect() as db:
                cursor = db.cursor()
                cursor.execute(
                    """
                    INSERT INTO traffic_snapshots (
                        total_vehicles,
                        traffic_density,
                        green_lane,
                        green_time,
                        final_signal,
                        lane_counts,
                        queue_metrics,
                        vehicle_types
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        state["totalVehicles"],
                        state["trafficDensity"],
                        state["greenLane"],
                        state["greenTime"],
                        state["finalSignal"],
                        json.dumps(state["laneCounts"]),
                        json.dumps(state["queueMetrics"]),
                        json.dumps(state["vehicleTypes"]),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO signal_events (
                        event_type,
                        lane_name,
                        signal_status,
                        green_time,
                        traffic_density
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        "signal_snapshot",
                        state["greenLane"],
                        state["finalSignal"],
                        state["greenTime"],
                        state["trafficDensity"],
                    ),
                )
                if state.get("emergencyActive"):
                    cursor.execute(
                        """
                        INSERT INTO emergency_events (
                            event_type,
                            lane_name,
                            details
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            "emergency_priority",
                            state["emergencyLane"],
                            json.dumps(
                                {
                                    "type": state["emergencyType"],
                                    "phase": state["priorityMode"],
                                    "signal": state["finalSignal"],
                                }
                            ),
                        ),
                    )
                db.commit()
            self.error = None
        except Exception as exc:
            self.available = False
            self.error = str(exc)

    def report(self):
        if not self.available:
            return {
                "enabled": self.enabled,
                "available": False,
                "error": self.error,
                "snapshots": 0,
                "averageVehicles": 0,
                "highDensityEvents": 0,
            }

        try:
            with self.connect() as db:
                cursor = db.cursor(dictionary=True)
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS snapshots,
                        COALESCE(ROUND(AVG(total_vehicles), 1), 0) AS averageVehicles,
                        SUM(CASE WHEN traffic_density = 'HIGH' THEN 1 ELSE 0 END) AS highDensityEvents
                    FROM traffic_snapshots
                    WHERE captured_at >= NOW() - INTERVAL 1 DAY
                    """
                )
                row = cursor.fetchone()
            return {
                "enabled": True,
                "available": True,
                "error": None,
                "snapshots": row["snapshots"],
                "averageVehicles": float(row["averageVehicles"]),
                "highDensityEvents": int(row["highDensityEvents"] or 0),
                "generatedAt": time.time(),
            }
        except Exception as exc:
            self.available = False
            self.error = str(exc)
            return self.report()
