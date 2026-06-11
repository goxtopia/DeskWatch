import httpx
import threading
import time
from PySide6.QtCore import QThread, Signal

class APIPollThread(QThread):
    status_received = Signal(dict)
    stats_received = Signal(dict)
    connection_changed = Signal(bool, str)  # (is_connected, error_message)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.is_running = True
        self.poll_interval = 4.0  # Poll every 4 seconds
        self.wakeup_event = threading.Event()

    def stop(self):
        self.is_running = False
        self.wakeup_event.set()

    def trigger_refresh(self):
        self.wakeup_event.set()

    def run(self):
        # Use a client session to reuse connection sockets
        with httpx.Client(timeout=2.0) as client:
            while self.is_running:
                self.wakeup_event.clear()
                server_url = self.config.server_url
                
                try:
                    # 1. Fetch camera status (which embeds sedentary status if capturing)
                    status_res = client.get(f"{server_url}/api/camera/status")
                    if status_res.status_code == 200:
                        status_data = status_res.json()
                        self.status_received.emit(status_data)
                        self.connection_changed.emit(True, "")
                    else:
                        self.connection_changed.emit(False, f"HTTP Error {status_res.status_code}")

                    # 2. Fetch daily stats for monitoring dashboard
                    stats_res = client.get(f"{server_url}/api/stats/daily")
                    if stats_res.status_code == 200:
                        stats_data = stats_res.json()
                        self.stats_received.emit(stats_data)
                except httpx.RequestError as e:
                    # User-friendly message for common connection failures
                    self.connection_changed.emit(False, "Server Offline / Connect Error")
                except Exception as e:
                    self.connection_changed.emit(False, f"Error: {str(e)}")

                # Wait for poll_interval, or wake up immediately if wakeup_event is set
                self.wakeup_event.wait(timeout=self.poll_interval)
