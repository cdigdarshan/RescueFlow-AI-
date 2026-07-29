import time

import cv2
from flask import Flask, Response, jsonify, render_template

from .analyzer import TrafficAnalyzer
from .config import DB_LOG_INTERVAL_SECONDS, LANES
from .database import TrafficDatabase


def create_app(source):
    flask_app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    analyzer = TrafficAnalyzer(source)
    database = TrafficDatabase()
    last_logged_at = {"value": 0}

    @flask_app.route("/")
    def dashboard():
        return render_template("dashboard.html", lanes=LANES)

    @flask_app.route("/video_feed")
    def video_feed():
        return Response(
            frame_stream(analyzer),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @flask_app.route("/stats")
    def stats():
        state = analyzer.stats()
        state["database"] = {
            "enabled": database.enabled,
            "available": database.available,
            "error": database.error,
        }
        now = time.time()
        if now - last_logged_at["value"] >= DB_LOG_INTERVAL_SECONDS:
            database.log_snapshot(state)
            last_logged_at["value"] = now
        return jsonify(state)

    @flask_app.route("/reports")
    def reports():
        return jsonify(database.report())

    return flask_app


def frame_stream(analyzer):
    cap = analyzer.open_capture()
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video source: {analyzer.source}")

    while True:
        ok, frame = cap.read()
        if not ok:
            cap.release()
            if analyzer.source == "webcam":
                time.sleep(0.5)
            cap = analyzer.open_capture()
            continue

        processed = analyzer.analyze_frame(frame)
        ok, buffer = cv2.imencode(".jpg", processed, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )
