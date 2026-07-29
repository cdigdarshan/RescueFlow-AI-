import itertools
import math


class CentroidTracker:
    def __init__(self, max_distance=80, max_missing=18):
        self.max_distance = max_distance
        self.max_missing = max_missing
        self.next_id = itertools.count(1)
        self.objects = {}

    def update(self, detections):
        assigned = {}
        unmatched_tracks = set(self.objects)
        unmatched_detections = set(range(len(detections)))

        pairs = []
        for track_id, track in self.objects.items():
            for index, detection in enumerate(detections):
                if track["label"] != detection["label"]:
                    continue
                distance = math.dist(track["centroid"], detection["centroid"])
                if distance <= self.max_distance:
                    pairs.append((distance, track_id, index))

        for _, track_id, index in sorted(pairs):
            if track_id not in unmatched_tracks or index not in unmatched_detections:
                continue
            self.objects[track_id].update(
                centroid=detections[index]["centroid"],
                label=detections[index]["label"],
                missed=0,
            )
            assigned[index] = track_id
            unmatched_tracks.remove(track_id)
            unmatched_detections.remove(index)

        for track_id in list(unmatched_tracks):
            self.objects[track_id]["missed"] += 1
            if self.objects[track_id]["missed"] > self.max_missing:
                del self.objects[track_id]

        for index in unmatched_detections:
            track_id = next(self.next_id)
            self.objects[track_id] = {
                "centroid": detections[index]["centroid"],
                "label": detections[index]["label"],
                "missed": 0,
            }
            assigned[index] = track_id

        return assigned
