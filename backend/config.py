import os
import json

CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "rtsp_url": "0",  # "0" represents the primary webcam
    "sample_interval": 10,  # in seconds
    "categories": [
        "Using Computer",
        "Looking at Phone",
        "Eating",
        "Away",
        "Drinking Water"
    ],
    "active_model": "clip",  # "clip", "vlm", or "cnn"
    "vlm_api_url": "https://api.openai.com/v1",
    "vlm_api_key": "",
    "vlm_model": "gpt-4o-mini",
    "vlm_prompt": "Identify the primary activity of the person in the image. You must choose exactly one category from this list: {categories}. Return a JSON object with keys 'label' and 'confidence'. Example: {{\"label\": \"Using Computer\", \"confidence\": 0.95}}",
    "clip_model_name": "MobileCLIP2-S0",
    "sedentary_reminder_enabled": True,
    "sedentary_threshold_minutes": 3,
    "min_break_detections": 5,
    "sedentary_snooze_minutes": 5,
    "telegram_bot_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_report_enabled": False,
    "telegram_report_time": "21:00",
    "drinking_categories": ["Drinking Water"],
    "drinking_merge_gap": 5
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            # Ensure all default keys are present
            updated = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
                    updated = True
            if updated:
                save_config(config)
            return config
    except Exception as e:
        print(f"Error loading config: {e}. Using defaults.")
        return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
