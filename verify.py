import os
import sys
import shutil

def main():
    print("=== DeskWatch Setup Verification ===")
    
    # 1. Check folder layout
    print("\n1. Checking files and folders structure:")
    required_paths = [
        "backend/config.py",
        "backend/db.py",
        "backend/classifiers.py",
        "backend/camera_worker.py",
        "backend/train_pipeline.py",
        "backend/main.py",
        "frontend/index.html",
        "frontend/style.css",
        "frontend/app.js"
    ]
    all_ok = True
    for p in required_paths:
        exists = os.path.exists(p)
        status = "OK" if exists else "MISSING"
        print(f"  - {p}: {status}")
        if not exists:
            all_ok = False
            
    if not all_ok:
        print("\n[ERROR] Some essential project files are missing!")
        sys.exit(1)
        
    # Add project root to path for imports
    sys.path.append(os.getcwd())
    
    # 2. Test Configuration Loader
    print("\n2. Testing Configuration Manager:")
    try:
        from backend.config import load_config, save_config
        config = load_config()
        print("  - Loaded default configuration successfully.")
        print(f"  - Active Model: {config.get('active_model')}")
        print(f"  - Sample Interval: {config.get('sample_interval')}s")
        print(f"  - Categories: {config.get('categories')}")
    except Exception as e:
        print(f"  - [ERROR] Failed to load/save config: {e}")
        sys.exit(1)
        
    # 3. Test SQLite DB Init & Record Insert
    print("\n3. Testing SQLite DB Utilities:")
    try:
        from backend.db import init_db, add_record, get_unreviewed_records, get_daily_stats
        init_db()
        print("  - Database initialized successfully.")
        
        # Insert a dummy record
        record_id = add_record(
            timestamp="2026-06-08 12:00:00",
            image_path="data/captured/dummy_verify.jpg",
            predicted_label="Using Computer",
            model_type="clip",
            confidence=0.92
        )
        print(f"  - Successfully added dummy record (ID: {record_id}).")
        
        # Read it back
        unreviewed = get_unreviewed_records()
        assert len(unreviewed) > 0, "No unreviewed records found"
        print(f"  - Retrieved {len(unreviewed)} unreviewed records.")
        
        # Check daily stats query
        stats = get_daily_stats("2026-06-08")
        print(f"  - Daily Stats query summary: {stats['summary']}")
        print(f"  - Daily Stats query timeline length: {len(stats['timeline'])}")
        
        # Check all records (pagination query)
        from backend.db import get_all_records
        all_records_res = get_all_records(limit=10, offset=0, reviewed=None)
        print(f"  - Paginated get_all_records query total count: {all_records_res['total']}")
        
        # Clean up dummy record
        from backend.db import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        print("  - Cleaned up dummy DB records.")
    except Exception as e:
        print(f"  - [ERROR] Database verification failed: {e}")
        sys.exit(1)
        
    # 4. Check ML imports
    print("\n4. Checking machine learning library availability:")
    try:
        import torch
        print(f"  - PyTorch version: {torch.__version__}")
        print(f"  - CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  - GPU Name: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("  - [WARNING] PyTorch is not yet available in the environment. Please wait for dependencies installation to complete.")
        
    try:
        import cv2
        print(f"  - OpenCV (cv2) version: {cv2.__version__}")
    except ImportError:
        print("  - [WARNING] OpenCV (cv2) is not yet available in the environment.")
        
    # 5. Check CLIP Classifiers and Model Config
    print("\n5. Checking CLIP neural network modules:")
    try:
        import torch
        from backend.classifiers import CLIPMLPClassifier, CLIPLinearClassifier
        mlp = CLIPMLPClassifier(input_dim=512, hidden_dim=128, num_classes=5)
        linear = CLIPLinearClassifier(input_dim=512, num_classes=5)
        dummy_input = torch.randn(2, 512)
        
        dummy_output_mlp = mlp(dummy_input)
        assert dummy_output_mlp.shape == (2, 5), f"Unexpected shape {dummy_output_mlp.shape}"
        print("  - CLIPMLPClassifier model forward pass: OK.")
        
        dummy_output_linear = linear(dummy_input)
        assert dummy_output_linear.shape == (2, 5), f"Unexpected shape {dummy_output_linear.shape}"
        print("  - CLIPLinearClassifier model forward pass: OK.")
    except Exception as e:
        print(f"  - [WARNING] CLIP classifiers check failed: {e}")
        
    print("\n=== SETUP VERIFICATION SUCCESSFUL ===")
    print("You can run the web server using:")
    print("  uv run backend/main.py")

if __name__ == "__main__":
    main()
