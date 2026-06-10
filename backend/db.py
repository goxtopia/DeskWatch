import os
import sqlite3
from datetime import datetime

DB_DIR = os.path.join("data", "db")
DB_PATH = os.path.join(DB_DIR, "deskwatch.db")

def get_safe_dir_name(label: str) -> str:
    if not label:
        return ""
    return label.replace("/", "_").replace("\\", "_").strip()

def migrate_dataset_folders():
    import shutil
    dataset_root = os.path.join("data", "dataset")
    if not os.path.exists(dataset_root):
        return
        
    print("[系统] 开始检查并迁移嵌套的类别数据集文件夹...")
    try:
        # Scan everything in dataset_root
        for item in os.listdir(dataset_root):
            item_path = os.path.join(dataset_root, item)
            if not os.path.isdir(item_path):
                continue
                
            cleaned_item = item.strip()
            
            # Check if this directory has subdirectories (e.g. Daydreaming / Thinking -> "Daydreaming " folder containing "Thinking" folder)
            try:
                subdirs = [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d))]
            except Exception:
                continue
                
            for subdir in subdirs:
                subdir_clean = subdir.strip()
                original_label = f"{cleaned_item} / {subdir_clean}"
                safe_folder_name = get_safe_dir_name(original_label)
                
                src_dir = os.path.join(item_path, subdir)
                dest_dir = os.path.join(dataset_root, safe_folder_name)
                os.makedirs(dest_dir, exist_ok=True)
                
                try:
                    files = os.listdir(src_dir)
                except Exception:
                    files = []
                    
                for f in files:
                    src_file = os.path.join(src_dir, f)
                    if os.path.isfile(src_file):
                        dest_file = os.path.join(dest_dir, f)
                        try:
                            shutil.move(src_file, dest_file)
                            print(f"[系统] 迁移嵌套文件: {src_file} -> {dest_file}")
                        except Exception as e:
                            print(f"[错误] 迁移文件失败 {src_file}: {e}")
                
                try:
                    os.rmdir(src_dir)
                except Exception as e:
                    print(f"[警告] 无法删除子目录 {src_dir}: {e}")
            
            try:
                if not os.listdir(item_path):
                    os.rmdir(item_path)
                    print(f"[系统] 清理空迁移文件夹: {item_path}")
            except Exception:
                pass
    except Exception as e:
        print(f"[错误] 文件夹迁移发生异常: {e}")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(os.path.join("data", "captured"), exist_ok=True)
    os.makedirs(os.path.join("data", "dataset"), exist_ok=True)
    
    migrate_dataset_folders()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            image_path TEXT NOT NULL,
            predicted_label TEXT NOT NULL,
            corrected_label TEXT,
            reviewed INTEGER DEFAULT 0,
            model_type TEXT NOT NULL,
            confidence REAL
        )
    """)
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def add_record(timestamp, image_path, predicted_label, model_type, confidence=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO records (timestamp, image_path, predicted_label, model_type, confidence)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp, image_path, predicted_label, model_type, confidence))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id

def get_unreviewed_records(limit=100):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM records
        WHERE reviewed = 0
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def review_record(record_id, corrected_label):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Retrieve details BEFORE updating so we know the previous corrected_label
    cursor.execute("SELECT image_path, timestamp, corrected_label, reviewed FROM records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    
    cursor.execute("""
        UPDATE records
        SET corrected_label = ?, reviewed = 1
        WHERE id = ?
    """, (corrected_label, record_id))
    
    conn.commit()
    conn.close()
    return row

def delete_record(record_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path, corrected_label, reviewed FROM records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if row:
        image_path = row["image_path"]
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as e:
                print(f"Error removing file {image_path}: {e}")
        
        # Also clean up from dataset if reviewed
        if row["reviewed"] == 1 and row["corrected_label"]:
            dataset_image_path = os.path.join("data", "dataset", get_safe_dir_name(row["corrected_label"]), os.path.basename(image_path))
            if os.path.exists(dataset_image_path):
                try:
                    os.remove(dataset_image_path)
                except Exception as e:
                    print(f"Error removing dataset file {dataset_image_path}: {e}")
                    
        cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.commit()
        success = True
    else:
        success = False
    conn.close()
    return success

def get_daily_stats(date_str=None):
    """
    Get activity counts grouped by label for a specific date (YYYY-MM-DD).
    If date_str is None, uses today's date in local time.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    # SQLite date function expects YYYY-MM-DD format
    cursor.execute("""
        SELECT 
            COALESCE(corrected_label, predicted_label) AS label,
            COUNT(*) AS count
        FROM records
        WHERE date(timestamp) = date(?)
        GROUP BY label
    """, (date_str,))
    
    rows = cursor.fetchall()
    stats = {row["label"]: row["count"] for row in rows}
    
    # Also fetch individual raw timelines for plotting a chronological activity graph
    cursor.execute("""
        SELECT 
            timestamp,
            COALESCE(corrected_label, predicted_label) AS label
        FROM records
        WHERE date(timestamp) = date(?)
        ORDER BY timestamp ASC
    """, (date_str,))
    
    timeline = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "date": date_str,
        "summary": stats,
        "timeline": timeline
    }

def get_dataset_stats():
    """
    Returns counts of reviewed images per label, which is useful for training.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            corrected_label AS label,
            COUNT(*) AS count
        FROM records
        WHERE reviewed = 1 AND corrected_label IS NOT NULL
        GROUP BY label
    """)
    rows = cursor.fetchall()
    stats = {row["label"]: row["count"] for row in rows}
    conn.close()
    return stats

def get_all_records(limit=60, offset=0, reviewed=None, date_str=None):
    """
    Get all records (reviewed or unreviewed) with pagination and filters.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM records WHERE 1=1"
    params = []
    
    if reviewed is not None:
        query += " AND reviewed = ?"
        params.append(reviewed)
    if date_str is not None:
        query += " AND date(timestamp) = date(?)"
        params.append(date_str)
        
    # Get total count first
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    
    # Get records ordered by timestamp descending
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "total": total_count,
        "records": rows
    }

def get_today_records():
    """
    Get all records (chronological order) for today.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            timestamp,
            COALESCE(corrected_label, predicted_label) AS label
        FROM records
        WHERE date(timestamp) = date(?)
        ORDER BY timestamp ASC
    """, (date_str,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

