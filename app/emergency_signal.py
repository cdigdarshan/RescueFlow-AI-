import math


class EmergencySignalController:
    """Fail-safe signal phases for a confirmed, tracked emergency vehicle."""

    NORMAL = "NORMAL"
    CLEARING = "CLEARING_CURRENT_GREEN"
    ALL_RED = "ALL_RED_SAFETY"
    EMERGENCY_GREEN = "EMERGENCY_GREEN"
    RECOVERY = "RECOVERY_ALL_RED"

    def __init__(self, yellow_seconds=4, all_red_seconds=2, recovery_seconds=2):
        self.yellow_seconds = yellow_seconds
        self.all_red_seconds = all_red_seconds
        self.recovery_seconds = recovery_seconds
        self.phase = self.NORMAL
        self.phase_started_at = 0
        self.target_lane = None
        self.clearing_lane = None
        self.last_emergency = None

    def update(self, normal_lane, normal_signal, emergency, now):
        previous_phase = self.phase

        if self.phase == self.NORMAL and emergency:
            self._capture_emergency(emergency)
            self.clearing_lane = normal_lane
            if normal_lane == emergency["lane"] and normal_signal == "GREEN":
                self._set_phase(self.EMERGENCY_GREEN, now)
            elif normal_signal == "RED":
                self._set_phase(self.ALL_RED, now)
            else:
                self._set_phase(self.CLEARING, now)

        elif self.phase == self.CLEARING:
            if emergency:
                self._capture_emergency(emergency)
            else:
                self._set_phase(self.RECOVERY, now)
            if self.phase == self.CLEARING and now - self.phase_started_at >= self.yellow_seconds:
                self._set_phase(self.ALL_RED, now)

        elif self.phase == self.ALL_RED:
            if emergency:
                self._capture_emergency(emergency)
            else:
                self._set_phase(self.RECOVERY, now)
            if self.phase == self.ALL_RED and now - self.phase_started_at >= self.all_red_seconds:
                self._set_phase(self.EMERGENCY_GREEN, now)

        elif self.phase == self.EMERGENCY_GREEN:
            if emergency:
                if emergency["lane"] != self.target_lane:
                    self.clearing_lane = self.target_lane
                    self._capture_emergency(emergency)
                    self._set_phase(self.CLEARING, now)
                else:
                    self._capture_emergency(emergency)
            else:
                self._set_phase(self.RECOVERY, now)

        elif self.phase == self.RECOVERY:
            if emergency:
                self._capture_emergency(emergency)
                self._set_phase(self.ALL_RED, now)
            elif now - self.phase_started_at >= self.recovery_seconds:
                self._set_phase(self.NORMAL, now)
                self.target_lane = None
                self.clearing_lane = None
                self.last_emergency = None

        result = self._result(normal_lane, normal_signal, now)
        result["normalResumed"] = previous_phase != self.NORMAL and self.phase == self.NORMAL
        return result

    def _capture_emergency(self, emergency):
        self.last_emergency = emergency.copy()
        self.target_lane = emergency["lane"]

    def _set_phase(self, phase, now):
        self.phase = phase
        self.phase_started_at = now

    def _remaining(self, duration, now):
        return max(0, int(math.ceil(duration - (now - self.phase_started_at))))

    def _result(self, normal_lane, normal_signal, now):
        if self.phase == self.NORMAL:
            lane = normal_lane
            signal = normal_signal
            active = False
            remaining = None
        elif self.phase == self.CLEARING:
            lane = self.clearing_lane
            signal = "YELLOW"
            active = True
            remaining = self._remaining(self.yellow_seconds, now)
        elif self.phase == self.ALL_RED:
            lane = self.target_lane
            signal = "RED"
            active = True
            remaining = self._remaining(self.all_red_seconds, now)
        elif self.phase == self.EMERGENCY_GREEN:
            lane = self.target_lane
            signal = "GREEN"
            active = True
            remaining = 0
        else:
            lane = self.target_lane or normal_lane
            signal = "RED"
            active = False
            remaining = self._remaining(self.recovery_seconds, now)

        emergency = self.last_emergency or {}
        return {
            "greenLane": lane,
            "finalSignal": signal,
            "secondsRemaining": remaining,
            "emergency": {
                "active": active,
                "lane": emergency.get("lane"),
                "type": emergency.get("type"),
                "phase": self.phase,
                "trackId": emergency.get("trackId"),
                "confidence": emergency.get("confidence"),
                "trackingStatus": emergency.get("status"),
            },
        }
