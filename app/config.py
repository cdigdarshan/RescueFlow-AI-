import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
DEFAULT_VIDEO = ASSETS_DIR / "videos" / "traffic_video.mp4"
MODEL_PATH = Path(os.environ.get("YOLO_MODEL_PATH", ASSETS_DIR / "models" / "yolov8n.pt"))
EMERGENCY_MODEL_PATH = Path(
    os.environ.get("EMERGENCY_MODEL_PATH", ASSETS_DIR / "models" / "ambulance.pt")
)

VEHICLE_CLASSES = {
    1: "Bicycle",
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    7: "Truck",
}

EMERGENCY_KEYWORDS = (
    "ambulance",
    "fire truck",
    "firetruck",
    "fire engine",
    "police",
    "police car",
    "emergency",
)

EMERGENCY_TRANSITION_SECONDS = 4
EMERGENCY_ALL_RED_SECONDS = float(os.environ.get("EMERGENCY_ALL_RED_SECONDS", "2"))
EMERGENCY_RECOVERY_SECONDS = float(os.environ.get("EMERGENCY_RECOVERY_SECONDS", "2"))
EMERGENCY_CONFIDENCE = float(os.environ.get("EMERGENCY_CONFIDENCE", "0.75"))
EMERGENCY_CONFIRM_FRAMES = int(os.environ.get("EMERGENCY_CONFIRM_FRAMES", "3"))
EMERGENCY_MAX_MISSED_FRAMES = int(os.environ.get("EMERGENCY_MAX_MISSED_FRAMES", "12"))
EMERGENCY_ENTRY_LINE_RATIO = float(os.environ.get("EMERGENCY_ENTRY_LINE_RATIO", "0.35"))
EMERGENCY_EXIT_LINE_RATIO = float(os.environ.get("EMERGENCY_EXIT_LINE_RATIO", "0.82"))
EMERGENCY_DIRECTION = os.environ.get("EMERGENCY_DIRECTION", "down").lower()

LANES = ("Lane A", "Lane B", "Lane C", "Lane D")

DENSITY_TIMINGS = {
    "LOW": 20,
    "MEDIUM": 35,
    "HIGH": 50,
}

LANE_COLORS = {
    "LOW": (47, 185, 132),
    "MEDIUM": (28, 193, 241),
    "HIGH": (56, 70, 220),
}

SIGNAL_COLORS = {
    "GREEN": (47, 185, 132),
    "YELLOW": (28, 193, 241),
    "RED": (56, 70, 220),
}

AVERAGE_VEHICLE_LENGTH_METERS = 4.5
AVERAGE_WAIT_SECONDS_PER_VEHICLE = 3.3
DB_LOG_INTERVAL_SECONDS = 5

MYSQL_CONFIG = {
    "host": os.environ.get("DB_HOST"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}
