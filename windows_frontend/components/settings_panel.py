from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton
from PySide6.QtCore import Qt, Signal

class SettingsPanel(QFrame):
    """
    Settings panel overlay containing options to configure the client.
    Emits signals on save and cancel events.
    """
    save_clicked = Signal(str, bool, bool)  # (server_url, always_on_top, click_through)
    cancel_clicked = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.setObjectName("SettingsPanel")
        self.setProperty("interactive", True)
        
        self.setStyleSheet("""
            QFrame#SettingsPanel {
                background: rgba(30, 30, 40, 240);
                border-top: 1px solid rgba(255, 255, 255, 12);
                border-bottom: 1px solid rgba(255, 255, 255, 12);
            }
            QLabel {
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                background: transparent;
            }
            QLabel#Title {
                font-weight: bold;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 15);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #4FC3F7;
                background: rgba(255, 255, 255, 25);
            }
            QCheckBox {
                color: #e0e0e0;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                spacing: 6px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                background: rgba(255, 255, 255, 15);
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #4FC3F7;
                border-color: #4FC3F7;
                image: url(no_image_needed_draw_checkmark_manually); /* falls back to background on Windows */
            }
            QPushButton {
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 4px;
                color: #ffffff;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 25);
                border: 1px solid rgba(255, 255, 255, 40);
            }
            QPushButton#SaveBtn {
                background: #00897B;
                border: 1px solid #00897B;
            }
            QPushButton#SaveBtn:hover {
                background: #00a896;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("⚙️ Widget Settings")
        title.setObjectName("Title")
        layout.addWidget(title)

        # Server Host/Port Input
        server_layout = QVBoxLayout()
        server_layout.setSpacing(4)
        server_lbl = QLabel("Server Host:Port (servername)")
        self.server_input = QLineEdit()
        self.server_input.setProperty("interactive", True)
        self.server_input.setPlaceholderText("e.g. 127.0.0.1:8000")
        
        server_layout.addWidget(server_lbl)
        server_layout.addWidget(self.server_input)
        layout.addLayout(server_layout)

        # Checkboxes
        checkboxes_layout = QVBoxLayout()
        checkboxes_layout.setSpacing(6)
        
        self.ontop_cb = QCheckBox("Always on Top")
        self.ontop_cb.setProperty("interactive", True)
        
        self.clickthrough_cb = QCheckBox("Allow Mouse Click-Through")
        self.clickthrough_cb.setProperty("interactive", True)
        self.clickthrough_cb.setToolTip("When checked, mouse clicks will pass through empty areas")

        checkboxes_layout.addWidget(self.ontop_cb)
        checkboxes_layout.addWidget(self.clickthrough_cb)
        layout.addLayout(checkboxes_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("interactive", True)
        self.cancel_btn.clicked.connect(self._on_cancel)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("SaveBtn")
        self.save_btn.setProperty("interactive", True)
        self.save_btn.clicked.connect(self._on_save)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

        # Load values
        self.reset_inputs()

    def reset_inputs(self):
        """
        Loads user config preferences into fields.
        """
        # Strip protocol prefix to display raw host:port to the user
        url = self.config.server_url
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        self.server_input.setText(url)
        
        self.ontop_cb.setChecked(self.config.always_on_top)
        self.clickthrough_cb.setChecked(self.config.click_through)

    def _on_save(self):
        server_val = self.server_input.text().strip()
        ontop_val = self.ontop_cb.isChecked()
        clickthrough_val = self.clickthrough_cb.isChecked()
        self.save_clicked.emit(server_val, ontop_val, clickthrough_val)

    def _on_cancel(self):
        self.reset_inputs()
        self.cancel_clicked.emit()
