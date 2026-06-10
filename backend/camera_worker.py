import os
import time
import threading
import cv2
from datetime import datetime
from backend.config import load_config
from backend.events import event_bus
from backend.classifiers import classify_image

class CameraWorker:
    def __init__(self):
        self.thread = None
        self.is_running = False
        self.last_status = "Stopped"
        self.last_capture_time = None
        self.last_prediction = None
        self.last_error = None
        self._lock = threading.Lock()
        
    def start(self):
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self.last_status = "Starting..."
            self.last_error = None
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            print("Camera worker thread started.")
            
    def stop(self):
        with self._lock:
            if not self.is_running:
                return
            self.is_running = False
            self.last_status = "Stopping..."
            
    def get_status(self):
        with self._lock:
            status = {
                "is_running": self.is_running,
                "status": self.last_status,
                "last_capture_time": self.last_capture_time,
                "last_prediction": self.last_prediction,
                "last_error": self.last_error
            }
            if self.is_running:
                from backend.health_monitor import get_current_health_status
                status["sedentary_status"] = get_current_health_status()
            return status

    def _run(self):
        while True:
            # Check running state
            with self._lock:
                if not self.is_running:
                    self.last_status = "Stopped"
                    break
                    
            config = load_config()
            rtsp_url = config.get("rtsp_url", "0")
            interval = config.get("sample_interval", 10)
            
            # Parse webcam vs RTSP string
            try:
                camera_source = int(rtsp_url)
            except ValueError:
                camera_source = rtsp_url
                
            self.last_status = "Capturing..."
            
            cap = None
            success = False
            frame = None
            
            try:
                cap = cv2.VideoCapture(camera_source)
                if cap.isOpened():
                    # Webcams might need a moment to warm up/auto-expose.
                    # We read a few frames to flush the buffer and get a fresh frame.
                    warmup_frames = 5 if isinstance(camera_source, int) else 1
                    for _ in range(warmup_frames):
                        ret, f = cap.read()
                        if ret:
                            frame = f
                            success = True
                else:
                    raise Exception(f"Failed to open video source: {rtsp_url}")
            except Exception as e:
                self.last_error = str(e)
                self.last_status = "Error"
                print(f"Camera worker capture error: {e}")
            finally:
                if cap is not None:
                    cap.release()
                    
            if success and frame is not None:
                try:
                    # Resize frame (downsample)
                    h, w = frame.shape[:2]
                    max_dim = 640
                    if max(h, w) > max_dim:
                        scale = max_dim / max(h, w)
                        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                        
                    # Save frame
                    os.makedirs(os.path.join("data", "captured"), exist_ok=True)
                    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    filename = f"{timestamp_str}.jpg"
                    image_path = os.path.join("data", "captured", filename)
                    
                    # cv2 uses BGR, write as image
                    cv2.imwrite(image_path, frame)
                    
                    # DB Timestamp format
                    db_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Classify frame
                    self.last_status = "Classifying..."
                    predicted_label, confidence = classify_image(image_path, config)
                    
                    # Add to Database
                    from backend.db import add_record
                    add_record(
                        timestamp=db_timestamp,
                        image_path=image_path,
                        predicted_label=predicted_label,
                        model_type=config["active_model"],
                        confidence=confidence
                    )
                    
                    # Publish new_record event
                    try:
                        record_dict = {
                            "timestamp": db_timestamp,
                            "image_path": image_path,
                            "predicted_label": predicted_label,
                            "model_type": config["active_model"],
                            "confidence": confidence
                        }
                        event_bus.publish("new_record", record=record_dict)
                    except Exception as ev_err:
                        print(f"Error publishing new_record event: {ev_err}")
                    
                    with self._lock:
                        self.last_capture_time = db_timestamp
                        self.last_prediction = {
                            "label": predicted_label,
                            "confidence": confidence,
                            "image_path": image_path.replace("\\", "/") # Normalize slash for web serving
                        }
                        self.last_status = "Active"
                        self.last_error = None
                        
                    print(f"[{db_timestamp}] Captured image classified as: {predicted_label} (conf: {confidence:.2f})")
                    
                except Exception as e:
                    self.last_error = f"Classification/Save Error: {str(e)}"
                    self.last_status = "Error"
                    print(f"Camera worker processing error: {e}")
            else:
                if self.last_status != "Error":
                    self.last_status = "Disconnected"
                    
            # Sleep for the configured interval, checking running state periodically
            sleep_remaining = interval
            while sleep_remaining > 0:
                with self._lock:
                    if not self.is_running:
                        break
                # Sleep in small steps so we can stop quickly if requested
                sleep_step = min(1.0, sleep_remaining)
                time.sleep(sleep_step)
                sleep_remaining -= sleep_step

# Global worker instance
worker_instance = CameraWorker()
