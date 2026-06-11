from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from windows_frontend.components.animations import start_breathing, stop_breathing

class ReminderOverlay(QFrame):
    """
    Overlay widget that covers the dashboard/status area when a sedentary threshold is exceeded.
    Offers Snooze and Dismiss buttons. Marked as 'interactive'.
    """
    snooze_clicked = Signal(int)  # Emits snooze minutes (e.g., 10)
    dismiss_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReminderOverlay")
        self.setProperty("interactive", True)
        
        self.setStyleSheet("""
            QFrame#ReminderOverlay {
                background: rgba(183, 28, 28, 240); /* Solid alert crimson */
                border-radius: 12px;
                border: 1.5px solid #FF5252;
            }
            QLabel {
                color: #ffffff;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
                border: none;
            }
            QLabel#AlertTitle {
                font-weight: bold;
                font-size: 13px;
                color: #FFE082; /* Warm amber */
            }
            QLabel#AlertDesc {
                font-size: 11px;
                color: #ffffff;
            }
            QPushButton {
                background: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 35);
                border-color: rgba(255, 255, 255, 50);
            }
            QPushButton#SnoozeBtn {
                background: #FFE082;
                border: 1px solid #FFE082;
                color: #5D4037;
            }
            QPushButton#SnoozeBtn:hover {
                background: #FFF59D;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        # Alarm icon and header
        self.icon_label = QLabel("🚨 🪑 🚨")
        self.icon_label.setProperty("interactive", True)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("Sedentary Alert!")
        self.title_label.setObjectName("AlertTitle")
        self.title_label.setProperty("interactive", True)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.desc_label = QLabel("You have been sitting for 0 minutes.")
        self.desc_label.setObjectName("AlertDesc")
        self.desc_label.setProperty("interactive", True)
        self.desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.desc_label)

        # Button Controls
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.setAlignment(Qt.AlignCenter)

        self.snooze_btn = QPushButton("Snooze 10m")
        self.snooze_btn.setObjectName("SnoozeBtn")
        self.snooze_btn.setProperty("interactive", True)
        self.snooze_btn.clicked.connect(self._on_snooze)

        self.dismiss_btn = QPushButton("Dismiss")
        self.dismiss_btn.setProperty("interactive", True)
        self.dismiss_btn.clicked.connect(self._on_dismiss)

        btn_layout.addWidget(self.snooze_btn)
        btn_layout.addWidget(self.dismiss_btn)
        layout.addLayout(btn_layout)

    def set_duration(self, minutes):
        """
        Updates the notification description message with active sitting time.
        """
        self.desc_label.setText(f"You have been sitting for {minutes:.1f} mins.\nStand up and stretch!")

    def showEvent(self, event):
        super().showEvent(event)
        # Apply visual breathing effect on the title to capture attention
        start_breathing(self.title_label, start_val=0.4, end_val=1.0, duration=800)

    def hideEvent(self, event):
        super().hideEvent(event)
        # Clear the breathing effect when reminder is hidden
        stop_breathing(self.title_label)

    def _on_snooze(self):
        self.snooze_clicked.emit(10)

    def _on_dismiss(self):
        self.dismiss_clicked.emit()
