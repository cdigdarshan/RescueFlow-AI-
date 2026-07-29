from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from ultralytics import YOLO

from .config import EMERGENCY_KEYWORDS, LANES
from .lap_compat import ensure_lap_compatibility


@dataclass
class EmergencyTrack:
    track_id: int
    label: str
    bbox: tuple
    centroid: tuple
    confidence: float
    lane: str
    hits: int = 1
    missed: int = 0
    confirmed: bool = False
    status: str = "APPROACHING"
    cleared: bool = False

    def as_dict(self):
        return {
            "trackId": self.track_id,
            "type": self.label,
            "bbox": self.bbox,
            "centroid": self.centroid,
            "confidence": round(self.confidence, 3),
            "lane": self.lane,
            "status": self.status,
            "confirmed": self.confirmed,
        }


class EmergencyVehicleTracker:
    """Optional custom YOLO detector with persistent Ultralytics ByteTrack IDs."""

    def __init__(
        self,
        model_path,
        confidence=0.75,
        confirm_frames=3,
        max_missed_frames=12,
        entry_line_ratio=0.35,
        exit_line_ratio=0.82,
        direction="down",
    ):
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.confirm_frames = max(1, confirm_frames)
        self.max_missed_frames = max(0, max_missed_frames)
        self.entry_line_ratio = entry_line_ratio
        self.exit_line_ratio = exit_line_ratio
        self.direction = direction if direction in ("up", "down") else "down"
        self.tracks: Dict[int, EmergencyTrack] = {}
        self.model = None
        self.error = None

        if not self.model_path.is_file():
            return

        try:
            self.model = YOLO(str(self.model_path))
            names = self.model.names.values() if isinstance(self.model.names, dict) else self.model.names
            if not any(self._is_emergency_label(name) for name in names):
                self.error = "Emergency model has no ambulance or emergency class"
                self.model = None
        except Exception as exc:
            self.error = f"Unable to load emergency model: {exc}"

    @property
    def available(self):
        return self.model is not None

    def info(self):
        return {
            "available": self.available,
            "configured": self.model_path.is_file(),
            "modelPath": str(self.model_path),
            "error": self.error,
        }

    def process(self, frame):
        if not self.available:
            return [], None

        try:
            ensure_lap_compatibility()
            results = self.model.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=self.confidence,
                verbose=False,
            )
            detections = self._extract_detections(results)
        except Exception as exc:
            self.error = f"Emergency tracking failed: {exc}"
            self.model = None
            return [], None

        height, width = frame.shape[:2]
        return self.update_from_detections(detections, width, height)

    def update_from_detections(self, detections, frame_width, frame_height):
        seen_ids = set()
        visible_tracks: List[EmergencyTrack] = []

        for detection in detections:
            track_id = int(detection["track_id"])
            seen_ids.add(track_id)
            centroid = detection["centroid"]
            lane = self._lane_for_x(centroid[0], frame_width)
            status = self._status_for_y(centroid[1], frame_height)
            existing = self.tracks.get(track_id)

            if existing is None:
                existing = EmergencyTrack(
                    track_id=track_id,
                    label=detection["label"],
                    bbox=detection["bbox"],
                    centroid=centroid,
                    confidence=detection["confidence"],
                    lane=lane,
                    status=status,
                )
                self.tracks[track_id] = existing
            else:
                existing.label = detection["label"]
                existing.bbox = detection["bbox"]
                existing.centroid = centroid
                existing.confidence = detection["confidence"]
                existing.lane = lane
                existing.status = status
                existing.hits += 1
                existing.missed = 0

            existing.confirmed = existing.hits >= self.confirm_frames
            existing.cleared = status == "CLEARED"
            visible_tracks.append(existing)

        for track_id, track in list(self.tracks.items()):
            if track_id in seen_ids or track.cleared:
                continue
            track.missed += 1
            if not track.confirmed:
                track.hits = 0
            if track.missed > self.max_missed_frames:
                track.cleared = True
                track.status = "LOST"

        active_candidates = [
            track
            for track in self.tracks.values()
            if track.confirmed and not track.cleared and track.missed <= self.max_missed_frames
        ]
        active_track = max(
            active_candidates,
            key=lambda track: (track.status == "CROSSING", track.hits, track.confidence),
            default=None,
        )
        return [track.as_dict() for track in visible_tracks], (
            active_track.as_dict() if active_track else None
        )

    def _extract_detections(self, results):
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                if box.id is None:
                    continue
                class_id = int(box.cls.item())
                label = self._class_name(class_id)
                if not self._is_emergency_label(label):
                    continue
                x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
                detections.append(
                    {
                        "track_id": int(box.id.item()),
                        "label": label.title(),
                        "bbox": (x1, y1, x2, y2),
                        "centroid": ((x1 + x2) // 2, (y1 + y2) // 2),
                        "confidence": float(box.conf.item()),
                    }
                )
        return detections

    def _class_name(self, class_id):
        names = self.model.names
        if isinstance(names, dict):
            return names.get(class_id, str(class_id))
        if 0 <= class_id < len(names):
            return names[class_id]
        return str(class_id)

    def _is_emergency_label(self, label):
        normalized = label.lower().replace("_", " ").replace("-", " ")
        return any(keyword in normalized for keyword in EMERGENCY_KEYWORDS)

    def _lane_for_x(self, x, width):
        lane_width = width / len(LANES)
        index = min(max(int(x / lane_width), 0), len(LANES) - 1)
        return LANES[index]

    def _status_for_y(self, y, height):
        progress = y / max(height, 1)
        if self.direction == "up":
            progress = 1 - progress
        if progress >= self.exit_line_ratio:
            return "CLEARED"
        if progress >= self.entry_line_ratio:
            return "CROSSING"
        return "APPROACHING"
