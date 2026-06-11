import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_config.json")

class ClientConfigManager:
    def __init__(self):
        self.config = {
            "server_url": "http://127.0.0.1:8000",
            "always_on_top": True,
            "click_through": False,
            "window_x": None,
            "window_y": None
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Update default dict with loaded keys to ensure fallback values
                    self.config.update(loaded)
            except Exception as e:
                print(f"Error loading client config: {e}")

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving client config: {e}")

    @property
    def server_url(self) -> str:
        return self.config.get("server_url", "http://127.0.0.1:8000")

    @server_url.setter
    def server_url(self, val: str):
        # Normalize: ensure it starts with http:// or https://
        val = val.strip()
        if val and not val.startswith(("http://", "https://")):
            val = f"http://{val}"
        self.config["server_url"] = val
        self.save()

    @property
    def always_on_top(self) -> bool:
        return self.config.get("always_on_top", True)

    @always_on_top.setter
    def always_on_top(self, val: bool):
        self.config["always_on_top"] = bool(val)
        self.save()

    @property
    def click_through(self) -> bool:
        return self.config.get("click_through", False)

    @click_through.setter
    def click_through(self, val: bool):
        self.config["click_through"] = bool(val)
        self.save()

    @property
    def window_position(self):
        return self.config.get("window_x"), self.config.get("window_y")

    def set_window_position(self, x: int, y: int):
        self.config["window_x"] = x
        self.config["window_y"] = y
        self.save()
