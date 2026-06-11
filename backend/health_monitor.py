import logging
from datetime import datetime
from backend.events import event_bus
from backend.config import load_config
from backend.db import get_today_records

logger = logging.getLogger("deskwatch.health")

# In-memory store for the current health/sedentary state
_current_health_status = {
    "is_sedentary": False,
    "sedentary_minutes": 0.0,
    "inactive_minutes": 0.0,
    "last_break_time": None,
    "current_break_consecutive": 0
}

def get_current_health_status():
    global _current_health_status
    return _current_health_status

def analyze_health_status(records, config):
    """
    Analyzes today's chronological records and computes the sedentary reminder state.
    """
    enabled = config.get("sedentary_reminder_enabled", True)
    if not enabled or not records:
        return {
            "is_sedentary": False,
            "sedentary_minutes": 0.0,
            "inactive_minutes": 0.0,
            "last_break_time": None,
            "current_break_consecutive": 0
        }
        
    threshold_minutes = config.get("sedentary_threshold_minutes", 3)
    min_break_detections = config.get("min_break_detections", 5)
    break_categories = config.get("break_categories", ["Away", "Standing", "Napping"])
    sample_interval = config.get("sample_interval", 10)
    
    break_cats_lower = {cat.lower() for cat in break_categories}
    
    def is_break(label):
        if not label:
            return False
        return label.lower() in break_cats_lower
        
    n = len(records)
    if n == 0:
        return {
            "is_sedentary": False,
            "sedentary_minutes": 0.0,
            "last_break_time": None,
            "current_break_consecutive": 0
        }
    
    # 1. Scan backwards to find the current active continuous session
    # A gap larger than max(300, 5 * sample_interval) splits the session
    max_gap = max(300.0, 5.0 * sample_interval)
    session_start_idx = 0
    
    for i in range(n - 1, 0, -1):
        t_curr = datetime.strptime(records[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
        t_prev = datetime.strptime(records[i-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        if (t_curr - t_prev).total_seconds() > max_gap:
            session_start_idx = i
            break
            
    # Slice the records to only contain the current continuous session
    session_records = records[session_start_idx:]
    m = len(session_records)
    
    if m == 0:
        return {
            "is_sedentary": False,
            "sedentary_minutes": 0.0,
            "last_break_time": None,
            "current_break_consecutive": 0
        }
        
    # 2. Find contiguous break segments in the session
    break_segments = []  # List of tuples (start_idx, end_idx)
    in_break = False
    start_idx = -1
    
    for i in range(m):
        rec = session_records[i]
        label = rec.get("label")
        is_brk = is_break(label)
        
        if is_brk:
            if not in_break:
                in_break = True
                start_idx = i
        else:
            if in_break:
                break_segments.append((start_idx, i - 1))
                in_break = False
                
    if in_break:
        break_segments.append((start_idx, m - 1))
        
    # Filter valid break segments (length >= min_break_detections)
    valid_break_segments = []
    for start, end in break_segments:
        length = end - start + 1
        if length >= min_break_detections:
            valid_break_segments.append((start, end))
            
    # 3. Analyze current sedentary status
    if valid_break_segments:
        last_valid_start_idx, last_valid_end_idx = valid_break_segments[-1]
        
        # If the user is currently on a valid break, they are not sedentary
        if last_valid_end_idx == m - 1:
            last_rec = session_records[last_valid_end_idx]
            return {
                "is_sedentary": False,
                "sedentary_minutes": 0.0,
                "inactive_minutes": 0.0,
                "last_break_time": last_rec["timestamp"],
                "current_break_consecutive": last_valid_end_idx - last_valid_start_idx + 1
            }
            
        # Otherwise, the sedentary period started at the record immediately after the valid break
        last_break_rec = session_records[last_valid_end_idx]
        last_valid_end_time = last_break_rec["timestamp"]
        
        sedentary_start_rec = session_records[last_valid_end_idx + 1]
        sedentary_start_time = datetime.strptime(sedentary_start_rec["timestamp"], "%Y-%m-%d %H:%M:%S")
    else:
        # No valid breaks in the session
        # Sedentary period started at the first record of the session
        sedentary_start_rec = session_records[0]
        sedentary_start_time = datetime.strptime(sedentary_start_rec["timestamp"], "%Y-%m-%d %H:%M:%S")
        last_valid_end_time = None
        
    latest_rec = session_records[-1]
    latest_time = datetime.strptime(latest_rec["timestamp"], "%Y-%m-%d %H:%M:%S")
    
    duration_seconds = (latest_time - sedentary_start_time).total_seconds()
    sedentary_minutes = max(0.0, duration_seconds / 60.0)
    
    # Calculate inactive minutes since last break ended (or session started)
    if last_valid_end_time:
        last_break_dt = datetime.strptime(last_valid_end_time, "%Y-%m-%d %H:%M:%S")
        inactive_seconds = (latest_time - last_break_dt).total_seconds()
        inactive_minutes = max(0.0, inactive_seconds / 60.0)
    else:
        first_rec_dt = datetime.strptime(session_records[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
        inactive_seconds = (latest_time - first_rec_dt).total_seconds()
        inactive_minutes = max(0.0, inactive_seconds / 60.0)
        
    # Check if the user is currently on an active (but not yet valid) break segment
    current_break_consecutive = 0
    if break_segments:
        last_seg_start, last_seg_end = break_segments[-1]
        if last_seg_end == m - 1:
            current_break_consecutive = last_seg_end - last_seg_start + 1
            
    is_sedentary = sedentary_minutes >= threshold_minutes
    
    return {
        "is_sedentary": is_sedentary,
        "sedentary_minutes": round(sedentary_minutes, 1),
        "inactive_minutes": round(inactive_minutes, 1),
        "last_break_time": last_valid_end_time,
        "current_break_consecutive": current_break_consecutive
    }

def on_new_record(record):
    """
    Callback triggered when a new classification record is added.
    """
    global _current_health_status
    try:
        config = load_config()
        # Only process if reminder is enabled
        if not config.get("sedentary_reminder_enabled", True):
            _current_health_status = {
                "is_sedentary": False,
                "sedentary_minutes": 0.0,
                "inactive_minutes": 0.0,
                "last_break_time": None,
                "current_break_consecutive": 0
            }
            return
            
        records = get_today_records()
        new_status = analyze_health_status(records, config)
        
        old_sedentary = _current_health_status.get("is_sedentary", False)
        new_sedentary = new_status.get("is_sedentary", False)
        
        # Detect state transitions
        if new_sedentary and not old_sedentary:
            logger.info("Sedentary alert triggered!")
            event_bus.publish(
                "sedentary_alert", 
                sedentary_minutes=new_status["sedentary_minutes"],
                timestamp=record.get("timestamp")
            )
        elif not new_sedentary and old_sedentary:
            logger.info("Sedentary alert cleared!")
            event_bus.publish(
                "sedentary_clear",
                timestamp=record.get("timestamp")
            )
            
        _current_health_status = new_status
    except Exception as e:
        logger.error(f"Error in health monitor record callback: {e}", exc_info=True)

def init_health_monitor():
    """
    Subscribes the health monitor to event streams.
    """
    event_bus.subscribe("new_record", on_new_record)
    logger.info("Health monitor initialized and subscribed to new_record events.")


def calculate_sedentary_stats_for_today(records, config):
    """
    Computes today's total valid break count and sitting overtime minutes across all sessions today.
    Identical to the frontend dashboard.js calculateSedentaryStats logic.
    """
    if not records:
        return {"valid_breaks": 0, "overtime_minutes": 0}
        
    sample_interval = config.get("sample_interval", 10)
    min_break_detections = config.get("min_break_detections", 5)
    threshold_minutes = config.get("sedentary_threshold_minutes", 3)
    break_categories = config.get("break_categories", ["Away", "Standing", "Napping"])
    break_cats_lower = {cat.lower() for cat in break_categories}
    
    def is_break(label):
        if not label:
            return False
        return label.lower() in break_cats_lower
        
    def time_to_seconds(time_str):
        try:
            parts = time_str.split(" ")
            if len(parts) < 2:
                return 0
            time_parts = parts[1].split(":")
            return int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
        except Exception:
            return 0
            
    # 1. Group records into sessions based on sample gaps (> max_gap)
    max_gap = max(300.0, 5.0 * sample_interval)
    sessions = []
    current_session = [records[0]]
    
    for i in range(1, len(records)):
        prev_sec = time_to_seconds(records[i-1]["timestamp"])
        curr_sec = time_to_seconds(records[i]["timestamp"])
        if curr_sec - prev_sec > max_gap:
            sessions.append(current_session)
            current_session = []
        current_session.append(records[i])
    sessions.append(current_session)
    
    total_valid_breaks = 0
    total_overtime_seconds = 0.0
    
    # 2. Process each session
    for session in sessions:
        if not session:
            continue
            
        m = len(session)
        # Find break segments in this session
        break_segments = []
        in_break = False
        start_idx = -1
        
        for i in range(m):
            is_brk = is_break(session[i].get("label"))
            if is_brk:
                if not in_break:
                    in_break = True
                    start_idx = i
            else:
                if in_break:
                    break_segments.append((start_idx, i - 1))
                    in_break = False
        if in_break:
            break_segments.append((start_idx, m - 1))
            
        # Filter valid break segments (length >= min_break_detections)
        valid_break_segments = []
        for start, end in break_segments:
            length = end - start + 1
            if length >= min_break_detections:
                valid_break_segments.append((start, end))
                total_valid_breaks += 1
                
        # 3. Calculate sitting segments (separated by valid breaks)
        sitting_segments = []
        prev_end = -1
        for start, end in valid_break_segments:
            sitting_segments.append((prev_end + 1, start - 1))
            prev_end = end
        sitting_segments.append((prev_end + 1, m - 1))
        
        # For each sitting segment, calculate duration and see if it exceeds threshold
        for start, end in sitting_segments:
            if start > end:
                continue
            start_sec = time_to_seconds(session[start]["timestamp"])
            end_sec = time_to_seconds(session[end]["timestamp"]) + sample_interval
            duration_sec = end_sec - start_sec
            
            threshold_sec = threshold_minutes * 60.0
            if duration_sec > threshold_sec:
                total_overtime_seconds += (duration_sec - threshold_sec)
                
    return {
        "valid_breaks": total_valid_breaks,
        "overtime_minutes": round(total_overtime_seconds / 60.0)
    }


def calculate_drinking_count(records, config):
    if not records:
        return 0
        
    drink_cats = config.get("drinking_categories", ["Drinking Water"])
    drink_cats_lower = {c.lower() for c in drink_cats}
    merge_gap = config.get("drinking_merge_gap", 5)
    sample_interval = config.get("sample_interval", 10)
    
    def is_drink(label):
        if not label:
            return False
        return label.lower() in drink_cats_lower
        
    def time_to_seconds(time_str):
        try:
            parts = time_str.split(" ")
            if len(parts) < 2:
                return 0
            time_parts = parts[1].split(":")
            return int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
        except Exception:
            return 0
            
    drink_records = [r for r in records if is_drink(r.get("label"))]
    if not drink_records:
        return 0
        
    occurrences = 1
    max_allowed_diff = (merge_gap + 1) * sample_interval
    
    for i in range(1, len(drink_records)):
        prev_time = time_to_seconds(drink_records[i-1]["timestamp"])
        curr_time = time_to_seconds(drink_records[i]["timestamp"])
        
        if curr_time - prev_time > max_allowed_diff:
            occurrences += 1
            
    return occurrences

