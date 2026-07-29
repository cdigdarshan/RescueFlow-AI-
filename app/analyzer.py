import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import cv2
from ultralytics import YOLO

from .config import (
    AVERAGE_VEHICLE_LENGTH_METERS,
    AVERAGE_WAIT_SECONDS_PER_VEHICLE,
    DENSITY_TIMINGS,
    EMERGENCY_ALL_RED_SECONDS,
    EMERGENCY_CONFIDENCE,
    EMERGENCY_CONFIRM_FRAMES,
    EMERGENCY_DIRECTION,
    EMERGENCY_ENTRY_LINE_RATIO,
    EMERGENCY_KEYWORDS,
    EMERGENCY_MAX_MISSED_FRAMES,
    EMERGENCY_MODEL_PATH,
    EMERGENCY_RECOVERY_SECONDS,
    EMERGENCY_TRANSITION_SECONDS,
    EMERGENCY_EXIT_LINE_RATIO,
    LANE_COLORS,
    LANES,
    MODEL_PATH,
    SIGNAL_COLORS,
    VEHICLE_CLASSES,
)
from .emergency_signal import EmergencySignalController
from .emergency_tracker import EmergencyVehicleTracker
from .tracker import CentroidTracker


@dataclass
class TrafficState:
    total_current: int = 0
    total_unique: int = 0
    density: str = "LOW"
    green_lane: str = "Lane A"
    green_time: int = 20
    seconds_remaining: int = 0
    final_signal: str = "RED"
    emergency_active: bool = False
    emergency_lane: str = None
    emergency_type: str = None
    emergency_track_id: int = None
    emergency_confidence: float = None
    emergency_tracking_status: str = None
    emergency_detector: dict = field(default_factory=dict)
    priority_mode: str = "NORMAL"
    signal_status: dict = field(default_factory=lambda: {lane: "RED" for lane in LANES})
    queue_metrics: OrderedDict = field(
        default_factory=lambda: OrderedDict(
            (
                lane,
                {"vehicles": 0, "queueMeters": 0, "averageWaitSeconds": 0},
            )
            for lane in LANES
        )
    )
    lane_counts: OrderedDict = field(
        default_factory=lambda: OrderedDict((lane, 0) for lane in LANES)
    )
    unique_lane_counts: OrderedDict = field(
        default_factory=lambda: OrderedDict((lane, 0) for lane in LANES)
    )
    vehicle_types: OrderedDict = field(default_factory=OrderedDict)
    last_updated: float = field(default_factory=time.time)


class TrafficAnalyzer:
    def __init__(self, source):
        self.source = source
        self.model = YOLO(str(MODEL_PATH))
        self.emergency_tracker = EmergencyVehicleTracker(
            EMERGENCY_MODEL_PATH,
            confidence=EMERGENCY_CONFIDENCE,
            confirm_frames=EMERGENCY_CONFIRM_FRAMES,
            max_missed_frames=EMERGENCY_MAX_MISSED_FRAMES,
            entry_line_ratio=EMERGENCY_ENTRY_LINE_RATIO,
            exit_line_ratio=EMERGENCY_EXIT_LINE_RATIO,
            direction=EMERGENCY_DIRECTION,
        )
        self.emergency_controller = EmergencySignalController(
            yellow_seconds=EMERGENCY_TRANSITION_SECONDS,
            all_red_seconds=EMERGENCY_ALL_RED_SECONDS,
            recovery_seconds=EMERGENCY_RECOVERY_SECONDS,
        )
        self.state = TrafficState(emergency_detector=self.emergency_tracker.info())
        self.lock = threading.Lock()
        self.seen_vehicle_ids = set()
        self.seen_lane_ids = {lane: set() for lane in LANES}
        self.tracker = CentroidTracker()
        self.active_green_started_at = time.time()

    def open_capture(self):
        if self.source == "webcam":
            return cv2.VideoCapture(0)
        return cv2.VideoCapture(str(self.source))

    def density_for_count(self, count):
        if count <= 8:
            return "LOW"
        if count <= 18:
            return "MEDIUM"
        return "HIGH"

    def lane_density_for_count(self, count):
        if count <= 2:
            return "LOW"
        if count <= 5:
            return "MEDIUM"
        return "HIGH"

    def lane_for_x(self, x, width):
        lane_width = width / len(LANES)
        index = min(int(x / lane_width), len(LANES) - 1)
        return LANES[index]

    def final_signal_for(self, vehicle_count, green_time):
        if vehicle_count == 0:
            return "RED"
        elapsed = int(time.time() - self.active_green_started_at)
        if max(green_time - elapsed, 0) <= 4:
            return "YELLOW"
        return "GREEN"

    def seconds_remaining_for(self, green_time):
        elapsed = int(time.time() - self.active_green_started_at)
        return max(green_time - elapsed, 0)

    def update_signal_window(self, green_lane, green_time):
        elapsed = time.time() - self.active_green_started_at
        if green_lane != self.state.green_lane or elapsed >= green_time:
            self.active_green_started_at = time.time()

    def analyze_frame(self, frame):
        height, width = frame.shape[:2]
        results = self.model(frame, verbose=False)
        detections = self.extract_detections(results)
        self.assign_tracking_ids(detections)
        emergency_tracks, active_emergency = self.emergency_tracker.process(frame)

        lane_counts = OrderedDict((lane, 0) for lane in LANES)
        vehicle_types = OrderedDict((name, 0) for name in VEHICLE_CLASSES.values())
        emergency_detections = []

        for detection in detections:
            lane = self.lane_for_x(detection["centroid"][0], width)
            lane_counts[lane] += 1
            if detection["label"] not in vehicle_types:
                vehicle_types[detection["label"]] = 0
            vehicle_types[detection["label"]] += 1
            detection["lane"] = lane
            if detection["is_emergency"]:
                emergency_detections.append(detection)

        normal_green_lane = max(lane_counts, key=lane_counts.get) if detections else self.state.green_lane
        density = self.density_for_count(sum(lane_counts.values()))
        green_time = DENSITY_TIMINGS[density]
        if active_emergency is None and not self.emergency_tracker.available:
            active_emergency = self.fallback_emergency(emergency_detections, height)

        if self.emergency_controller.phase == self.emergency_controller.NORMAL and active_emergency is None:
            self.update_signal_window(normal_green_lane, green_time)
        normal_signal = self.final_signal_for(sum(lane_counts.values()), green_time)
        signal_result = self.emergency_controller.update(
            normal_green_lane,
            normal_signal,
            active_emergency,
            time.time(),
        )
        green_lane = signal_result["greenLane"]
        final_signal = signal_result["finalSignal"]
        emergency_state = signal_result["emergency"]
        if signal_result["normalResumed"]:
            self.active_green_started_at = time.time()
            final_signal = "GREEN" if detections else "RED"
        seconds_remaining = signal_result["secondsRemaining"]
        if seconds_remaining is None:
            seconds_remaining = self.seconds_remaining_for(green_time)
        elif signal_result["normalResumed"]:
            seconds_remaining = green_time
        queue_metrics = self.queue_metrics_for(lane_counts)

        self.draw_detections(frame, detections, lane_counts)
        self.draw_emergency_tracks(frame, emergency_tracks, active_emergency)
        self.update_state(
            lane_counts,
            queue_metrics,
            vehicle_types,
            density,
            green_lane,
            green_time,
            seconds_remaining,
            final_signal,
            emergency_state,
        )
        return frame

    def extract_detections(self, results):
        detections = []
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                model_label = self.model.names.get(class_id, str(class_id))
                label = self.detection_label(class_id, model_label)
                if not label:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(
                    {
                        "bbox": (x1, y1, x2, y2),
                        "centroid": ((x1 + x2) // 2, (y1 + y2) // 2),
                        "label": label,
                        "track_id": None,
                        "confidence": float(box.conf[0]),
                        "lane": None,
                        "is_emergency": self.is_emergency_label(model_label),
                    }
                )
        return detections

    def detection_label(self, class_id, model_label):
        if self.is_emergency_label(model_label):
            return model_label.title()
        return VEHICLE_CLASSES.get(class_id)

    def is_emergency_label(self, label):
        normalized = label.lower().replace("_", " ").replace("-", " ")
        return any(keyword in normalized for keyword in EMERGENCY_KEYWORDS)

    def fallback_emergency(self, emergency_detections, frame_height):
        if not emergency_detections:
            return None
        detection = max(emergency_detections, key=lambda item: item["confidence"])
        status = self.emergency_tracker._status_for_y(
            detection["centroid"][1], frame_height
        )
        if status == "CLEARED":
            return None
        return {
            "trackId": detection["track_id"],
            "type": detection["label"],
            "bbox": detection["bbox"],
            "centroid": detection["centroid"],
            "confidence": round(detection["confidence"], 3),
            "lane": detection["lane"],
            "status": status,
            "confirmed": True,
        }

    def assign_tracking_ids(self, detections):
        fallback_ids = self.tracker.update(detections)
        for index, track_id in fallback_ids.items():
            detections[index]["track_id"] = track_id

    def draw_detections(self, frame, detections, lane_counts):
        for detection in detections:
            x1, y1, x2, y2 = detection["bbox"]
            lane = detection["lane"]
            vehicle_id = detection["track_id"]
            label = detection["label"]

            self.seen_vehicle_ids.add(vehicle_id)
            self.seen_lane_ids[lane].add(vehicle_id)

            lane_density = self.lane_density_for_count(lane_counts[lane])
            color = SIGNAL_COLORS["RED"] if detection["is_emergency"] else LANE_COLORS[lane_density]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            cv2.circle(frame, detection["centroid"], 4, (255, 255, 255), -1)
            cv2.putText(
                frame,
                f"{label} #{vehicle_id}",
                (x1, max(y1 - 10, 24)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
                cv2.LINE_AA,
            )

    def draw_emergency_tracks(self, frame, tracks, active_emergency):
        if not tracks:
            return

        height, width = frame.shape[:2]
        active_id = active_emergency["trackId"] if active_emergency else None
        for track in tracks:
            x1, y1, x2, y2 = track["bbox"]
            active = track["trackId"] == active_id
            color = (40, 40, 240) if active else (30, 150, 245)
            thickness = 4 if active else 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            label = (
                f"{track['type']} E#{track['trackId']} "
                f"{track['confidence']:.0%} {track['status']}"
            )
            label_y = min(y2 + 24, height - 8)
            cv2.putText(
                frame,
                label,
                (x1, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                color,
                2,
                cv2.LINE_AA,
            )

        if active_emergency:
            lane_index = LANES.index(active_emergency["lane"])
            lane_width = width // len(LANES)
            lane_x1 = lane_index * lane_width
            lane_x2 = width if lane_index == len(LANES) - 1 else (lane_index + 1) * lane_width
            entry_y = self.emergency_line_y(height, EMERGENCY_ENTRY_LINE_RATIO)
            exit_y = self.emergency_line_y(height, EMERGENCY_EXIT_LINE_RATIO)
            cv2.line(frame, (lane_x1, entry_y), (lane_x2, entry_y), (30, 190, 245), 2)
            cv2.line(frame, (lane_x1, exit_y), (lane_x2, exit_y), (40, 40, 240), 2)

    def emergency_line_y(self, height, progress_ratio):
        if EMERGENCY_DIRECTION == "up":
            progress_ratio = 1 - progress_ratio
        return int(height * progress_ratio)

    def queue_metrics_for(self, lane_counts):
        return OrderedDict(
            (
                lane,
                {
                    "vehicles": count,
                    "queueMeters": round(count * AVERAGE_VEHICLE_LENGTH_METERS, 1),
                    "averageWaitSeconds": int(round(count * AVERAGE_WAIT_SECONDS_PER_VEHICLE)),
                },
            )
            for lane, count in lane_counts.items()
        )

    def update_state(self, lane_counts, queue_metrics, vehicle_types, density, green_lane, green_time, seconds_remaining, final_signal, emergency_state):
        signal_status = {
            lane: final_signal if lane == green_lane else "RED" for lane in LANES
        }
        with self.lock:
            self.state = TrafficState(
                total_current=sum(lane_counts.values()),
                total_unique=len(self.seen_vehicle_ids),
                density=density,
                green_lane=green_lane,
                green_time=green_time,
                seconds_remaining=seconds_remaining,
                final_signal=final_signal,
                emergency_active=emergency_state["active"],
                emergency_lane=emergency_state["lane"],
                emergency_type=emergency_state["type"],
                emergency_track_id=emergency_state["trackId"],
                emergency_confidence=emergency_state["confidence"],
                emergency_tracking_status=emergency_state["trackingStatus"],
                emergency_detector=self.emergency_tracker.info(),
                priority_mode=emergency_state["phase"],
                signal_status=signal_status,
                queue_metrics=queue_metrics,
                lane_counts=lane_counts,
                unique_lane_counts=OrderedDict(
                    (lane, len(self.seen_lane_ids[lane])) for lane in LANES
                ),
                vehicle_types=vehicle_types,
                last_updated=time.time(),
            )

    def stats(self):
        with self.lock:
            return {
                "totalVehicles": self.state.total_current,
                "totalUniqueVehicles": self.state.total_unique,
                "trafficDensity": self.state.density,
                "greenLane": self.state.green_lane,
                "greenTime": self.state.green_time,
                "secondsRemaining": self.state.seconds_remaining,
                "finalSignal": self.state.final_signal,
                "emergencyActive": self.state.emergency_active,
                "emergencyLane": self.state.emergency_lane,
                "emergencyType": self.state.emergency_type,
                "emergencyTrackId": self.state.emergency_track_id,
                "emergencyConfidence": self.state.emergency_confidence,
                "emergencyTrackingStatus": self.state.emergency_tracking_status,
                "emergencyDetector": self.state.emergency_detector,
                "priorityMode": self.state.priority_mode,
                "signalStatus": self.state.signal_status,
                "queueMetrics": self.state.queue_metrics,
                "laneCounts": self.state.lane_counts,
                "uniqueLaneCounts": self.state.unique_lane_counts,
                "vehicleTypes": self.state.vehicle_types,
                "lastUpdated": self.state.last_updated,
            }
