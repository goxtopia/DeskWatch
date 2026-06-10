import os
import shutil
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from backend.config import load_config, save_config
from backend.db import (
    init_db,
    get_unreviewed_records,
    review_record,
    delete_record,
    get_daily_stats,
    get_dataset_stats,
    get_all_records,
    get_safe_dir_name
)
from backend.camera_worker import worker_instance
from backend.train_pipeline import start_training_in_background, get_training_status

app = FastAPI(title="DeskWatch API", version="1.0.0")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConfigSchema(BaseModel):
    rtsp_url: str
    sample_interval: int
    categories: List[str]
    active_model: str
    vlm_api_url: str
    vlm_api_key: str
    vlm_model: str
    vlm_prompt: str
    clip_model_name: str
    sedentary_reminder_enabled: bool
    sedentary_threshold_minutes: int
    min_break_detections: int
    break_categories: List[str]
    sedentary_snooze_minutes: int
    telegram_bot_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_report_enabled: bool
    telegram_report_time: str
    drinking_categories: List[str]
    drinking_merge_gap: int


class ReviewSchema(BaseModel):
    corrected_label: str

class TrainSchema(BaseModel):
    epochs: Optional[int] = 5
    batch_size: Optional[int] = 8
    lr: Optional[float] = 1e-4
    train_type: Optional[str] = "cnn"

@app.on_event("startup")
def startup_event():
    # Ensure database and directories are initialized
    init_db()
    
    # Initialize health monitor
    from backend.health_monitor import init_health_monitor
    init_health_monitor()
    
    # Initialize telegram bot
    from backend.telegram_bot import init_telegram_bot
    init_telegram_bot()
    
    # Auto-start camera worker
    config = load_config()
    worker_instance.start()
    print("DeskWatch server initialized, health monitor, telegram bot, and camera worker started.")

@app.on_event("shutdown")
def shutdown_event():
    worker_instance.stop()
    from backend.telegram_bot import stop_telegram_bot
    stop_telegram_bot()
    print("Camera worker and Telegram Bot stopped.")

@app.get("/api/config")
def get_config_endpoint():
    return load_config()

@app.post("/api/config")
def update_config_endpoint(new_config: ConfigSchema):
    # Validate CNN model availability if switching to CNN or CLIP-MLP
    if new_config.active_model == "cnn":
        model_path = os.path.join("models", "cnn_classifier.pth")
        labels_path = os.path.join("models", "cnn_labels.json")
        if not os.path.exists(model_path) or not os.path.exists(labels_path):
            raise HTTPException(
                status_code=400, 
                detail="CNN model has not been trained yet. Please correct some images and train a model first."
            )
    elif new_config.active_model == "clip_mlp":
        model_path = os.path.join("models", "clip_mlp_classifier.pth")
        labels_path = os.path.join("models", "clip_mlp_labels.json")
        if not os.path.exists(model_path) or not os.path.exists(labels_path):
            raise HTTPException(
                status_code=400, 
                detail="CLIP-MLP model has not been trained yet. Please correct some images and train a model first."
            )
            
    # Save the config
    success = save_config(new_config.dict())
    if not success:
        raise HTTPException(status_code=500, detail="Failed to write configuration file.")
        
    # Apply interval changes to the running worker by restarting it if it is running
    status = worker_instance.get_status()
    if status["is_running"]:
        worker_instance.stop()
        worker_instance.start()
        
    return {"status": "success", "config": load_config()}

@app.get("/api/camera/status")
def get_camera_status():
    return worker_instance.get_status()

@app.post("/api/camera/start")
def start_camera():
    worker_instance.start()
    return {"status": "success", "message": "Camera capture started."}

@app.post("/api/camera/stop")
def stop_camera():
    worker_instance.stop()
    return {"status": "success", "message": "Camera capture stopped."}

@app.get("/api/records/unreviewed")
def get_unreviewed_records_endpoint(limit: int = 100):
    return get_unreviewed_records(limit=limit)

@app.get("/api/records")
def get_all_records_endpoint(
    limit: int = 60,
    offset: int = 0,
    reviewed: Optional[int] = Query(None, description="0 for unreviewed, 1 for reviewed"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    return get_all_records(limit=limit, offset=offset, reviewed=reviewed, date_str=date)

@app.post("/api/records/{record_id}/review")
def review_record_endpoint(record_id: int, payload: ReviewSchema):
    # Update SQLite database
    row = review_record(record_id, payload.corrected_label)
    if not row:
        raise HTTPException(status_code=404, detail="Record not found.")
        
    image_path = row["image_path"]
    filename = os.path.basename(image_path)
    
    # If already reviewed and corrected label changed, delete old image from dataset
    if row["reviewed"] == 1 and row["corrected_label"] != payload.corrected_label:
        old_label = row["corrected_label"]
        if old_label:
            old_dest_path = os.path.join("data", "dataset", get_safe_dir_name(old_label), filename)
            if os.path.exists(old_dest_path):
                try:
                    os.remove(old_dest_path)
                except Exception as e:
                    print(f"Error removing old dataset file during re-review: {e}")
                    
    # Copy file to the training dataset directory
    if os.path.exists(image_path):
        try:
            dest_dir = os.path.join("data", "dataset", get_safe_dir_name(payload.corrected_label))
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, filename)
            shutil.copy2(image_path, dest_path)
        except Exception as e:
            print(f"Error copying image to training dataset: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to copy image to dataset folder: {str(e)}")
    else:
        print(f"Warning: Image file not found at {image_path} during review.")
        
    return {"status": "success", "message": "Record reviewed and added to dataset."}

@app.delete("/api/records/{record_id}")
def delete_record_endpoint(record_id: int):
    success = delete_record(record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found.")
    return {"status": "success", "message": "Record and image deleted."}

@app.get("/api/stats/daily")
def get_daily_stats_endpoint(date: Optional[str] = None):
    # Returns summary (counts) and chronological timeline
    return get_daily_stats(date_str=date)

@app.get("/api/stats/dataset")
def get_dataset_stats_endpoint():
    # Returns how many reviewed images exist per category
    return get_dataset_stats()

@app.post("/api/train")
def train_model(payload: TrainSchema):
    # Safety checks
    dataset_root = os.path.join("data", "dataset")
    if not os.path.exists(dataset_root):
        raise HTTPException(status_code=400, detail="Dataset is empty. Please review some records first.")
        
    categories = [d for d in os.listdir(dataset_root) if os.path.isdir(os.path.join(dataset_root, d))]
    if len(categories) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 categories with corrected images to train a classifier.")
        
    success, message = start_training_in_background(
        epochs=payload.epochs,
        batch_size=payload.batch_size,
        lr=payload.lr,
        train_type=payload.train_type
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
        
    return {"status": "success", "message": message}

@app.get("/api/train/status")
def get_train_status_endpoint():
    return get_training_status()

# Ensure folders exist for static mounts
os.makedirs(os.path.join("data", "captured"), exist_ok=True)
os.makedirs("frontend", exist_ok=True)

# Mount captured images folder at /data/captured
app.mount("/data/captured", StaticFiles(directory=os.path.join("data", "captured")), name="captured")

# Mount frontend directory at root /
# Make sure to create files in frontend/ before running, or FastAPI will throw error.
# We will create frontend/index.html shortly.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
