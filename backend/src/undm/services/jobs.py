"""Deployments running in this application process, each with its stop signal."""

from __future__ import annotations

import threading

from undm.orchestration.deployment import StopSignal


class DeploymentJobs:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[str, StopSignal] = {}

    def claim(self, deployment_id: str, signal: StopSignal | None = None
              ) -> StopSignal | None:
        """Register a run; None if this deployment is already running here. The steps of
        a staging plan share one signal, so a stop also keeps the later steps from running."""
        with self._lock:
            if deployment_id in self._running:
                return None
            signal = signal or StopSignal()
            self._running[deployment_id] = signal
            return signal

    def release(self, deployment_id: str) -> None:
        with self._lock:
            self._running.pop(deployment_id, None)

    def is_running(self, deployment_id: str) -> bool:
        with self._lock:
            return deployment_id in self._running

    def request_stop(self, deployment_id: str, by: str) -> bool:
        """Ask a running deployment to stop; False if it is not running here."""
        with self._lock:
            signal = self._running.get(deployment_id)
        if signal is None:
            return False
        signal.request(by)
        return True

    def stop_all(self, by: str) -> None:
        with self._lock:
            signals = list(self._running.values())
        for signal in signals:
            signal.request(by)
