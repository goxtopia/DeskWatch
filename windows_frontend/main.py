import sys
import os

# Resolve the project root path and append to sys.path so direct execution works
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from windows_frontend.config import ClientConfigManager
from windows_frontend.main_window import DeskWatchWidget

def main():
    # Configure high-DPI scale factor behavior for high-resolution displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("DeskWatchWidget")
    app.setApplicationDisplayName("DeskWatch Widget")
    
    # Initialize local configurations
    config_mgr = ClientConfigManager()
    
    # Initialize and display the main floating widget
    widget = DeskWatchWidget(config_mgr)
    widget.show()
    
    # Start the event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
