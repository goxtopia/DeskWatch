from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

class DragHandle(QFrame):
    """
    A widget that acts as the title bar and drag handle.
    Marked with the 'drag_handle' property so the hit test recognizes it.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DragHandle")
        self.setProperty("drag_handle", True)
        self.setFixedHeight(26)
        
        self.setStyleSheet("""
            QFrame#DragHandle {
                background: rgba(255, 255, 255, 12);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 12);
            }
            QLabel {
                color: rgba(255, 255, 255, 180);
                font-size: 10px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
                border: none;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # Title text label
        self.title_label = QLabel("DeskWatch")
        self.title_label.setProperty("drag_handle", True)

        # Visual indicator dots representing standard window drag grip
        self.grip_label = QLabel("⠿")
        self.grip_label.setProperty("drag_handle", True)
        self.grip_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.grip_label)
