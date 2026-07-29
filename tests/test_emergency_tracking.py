import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.emergency_signal import EmergencySignalController
from app.emergency_tracker import EmergencyVehicleTracker
from app.lap_compat import ensure_lap_compatibility


def detection(track_id=7, x=250, y=200, confidence=0.91):
    return {
        "track_id": track_id,
        "label": "Ambulance",
        "bbox": (x - 20, y - 20, x + 20, y + 20),
        "centroid": (x, y),
        "confidence": confidence,
    }


class EmergencyVehicleTrackerTests(unittest.TestCase):
    def make_tracker(self, **overrides):
        options = {
            "model_path": Path(tempfile.gettempdir()) / "missing-ambulance-model.pt",
            "confirm_frames": 3,
            "max_missed_frames": 2,
            "entry_line_ratio": 0.35,
            "exit_line_ratio": 0.82,
        }
        options.update(overrides)
        return EmergencyVehicleTracker(**options)

    def test_missing_custom_model_does_not_break_tracker(self):
        tracker = self.make_tracker()

        self.assertFalse(tracker.available)
        self.assertFalse(tracker.info()["configured"])
        self.assertEqual(tracker.process(object()), ([], None))

    def test_track_requires_confirmation_and_follows_entry_exit_lines(self):
        tracker = self.make_tracker()

        _, active = tracker.update_from_detections([detection()], 800, 1000)
        self.assertIsNone(active)
        tracker.update_from_detections([detection()], 800, 1000)
        visible, active = tracker.update_from_detections([detection()], 800, 1000)

        self.assertTrue(visible[0]["confirmed"])
        self.assertEqual(active["trackId"], 7)
        self.assertEqual(active["lane"], "Lane B")
        self.assertEqual(active["status"], "APPROACHING")

        _, active = tracker.update_from_detections([detection(y=500)], 800, 1000)
        self.assertEqual(active["status"], "CROSSING")

        _, active = tracker.update_from_detections([detection(y=850)], 800, 1000)
        self.assertIsNone(active)
        self.assertEqual(tracker.tracks[7].status, "CLEARED")

    def test_confirmed_track_survives_brief_detection_loss(self):
        tracker = self.make_tracker(confirm_frames=2, max_missed_frames=2)
        tracker.update_from_detections([detection()], 800, 1000)
        tracker.update_from_detections([detection()], 800, 1000)

        _, active = tracker.update_from_detections([], 800, 1000)
        self.assertIsNotNone(active)
        tracker.update_from_detections([], 800, 1000)
        _, active = tracker.update_from_detections([], 800, 1000)
        self.assertIsNone(active)
        self.assertEqual(tracker.tracks[7].status, "LOST")

    def test_scipy_assignment_fallback_supports_ultralytics_bytetrack(self):
        ensure_lap_compatibility()
        from ultralytics.trackers.utils.matching import linear_assignment

        matches, unmatched_rows, unmatched_columns = linear_assignment(
            np.array([[0.1, 0.9], [0.8, 0.2]]),
            thresh=0.5,
        )

        self.assertEqual(matches, [[0, 0], [1, 1]])
        self.assertEqual(len(unmatched_rows), 0)
        self.assertEqual(len(unmatched_columns), 0)


class EmergencySignalControllerTests(unittest.TestCase):
    emergency = {
        "trackId": 7,
        "type": "Ambulance",
        "lane": "Lane C",
        "confidence": 0.91,
        "status": "APPROACHING",
    }

    def test_safe_priority_and_recovery_sequence(self):
        controller = EmergencySignalController(
            yellow_seconds=4,
            all_red_seconds=2,
            recovery_seconds=2,
        )

        result = controller.update("Lane A", "GREEN", self.emergency, now=0)
        self.assertEqual(result["emergency"]["phase"], controller.CLEARING)
        self.assertEqual(result["finalSignal"], "YELLOW")
        self.assertEqual(result["greenLane"], "Lane A")

        result = controller.update("Lane A", "GREEN", self.emergency, now=4)
        self.assertEqual(result["emergency"]["phase"], controller.ALL_RED)
        self.assertEqual(result["finalSignal"], "RED")

        result = controller.update("Lane A", "GREEN", self.emergency, now=6)
        self.assertEqual(result["emergency"]["phase"], controller.EMERGENCY_GREEN)
        self.assertEqual(result["greenLane"], "Lane C")
        self.assertEqual(result["finalSignal"], "GREEN")

        result = controller.update("Lane A", "GREEN", None, now=7)
        self.assertEqual(result["emergency"]["phase"], controller.RECOVERY)
        self.assertEqual(result["finalSignal"], "RED")

        result = controller.update("Lane B", "GREEN", None, now=9)
        self.assertEqual(result["emergency"]["phase"], controller.NORMAL)
        self.assertEqual(result["greenLane"], "Lane B")
        self.assertTrue(result["normalResumed"])

    def test_existing_green_lane_can_enter_emergency_green_directly(self):
        controller = EmergencySignalController()
        emergency = dict(self.emergency, lane="Lane A")

        result = controller.update("Lane A", "GREEN", emergency, now=10)

        self.assertEqual(result["emergency"]["phase"], controller.EMERGENCY_GREEN)
        self.assertEqual(result["finalSignal"], "GREEN")

    def test_lost_emergency_during_clearing_enters_all_red_recovery(self):
        controller = EmergencySignalController()
        controller.update("Lane A", "GREEN", self.emergency, now=0)

        result = controller.update("Lane A", "GREEN", None, now=1)

        self.assertEqual(result["emergency"]["phase"], controller.RECOVERY)
        self.assertEqual(result["finalSignal"], "RED")
        self.assertFalse(result["emergency"]["active"])

    def test_emergency_lane_change_is_cleared_before_green_transfer(self):
        controller = EmergencySignalController(
            yellow_seconds=4,
            all_red_seconds=2,
            recovery_seconds=2,
        )
        first_emergency = dict(self.emergency, lane="Lane A")
        next_emergency = dict(self.emergency, lane="Lane C", trackId=8)
        controller.update("Lane A", "GREEN", first_emergency, now=0)

        result = controller.update("Lane A", "GREEN", next_emergency, now=1)
        self.assertEqual(result["emergency"]["phase"], controller.CLEARING)
        self.assertEqual(result["greenLane"], "Lane A")
        self.assertEqual(result["finalSignal"], "YELLOW")

        result = controller.update("Lane A", "GREEN", next_emergency, now=5)
        self.assertEqual(result["emergency"]["phase"], controller.ALL_RED)
        self.assertEqual(result["finalSignal"], "RED")

        result = controller.update("Lane A", "GREEN", next_emergency, now=7)
        self.assertEqual(result["emergency"]["phase"], controller.EMERGENCY_GREEN)
        self.assertEqual(result["greenLane"], "Lane C")


if __name__ == "__main__":
    unittest.main()
