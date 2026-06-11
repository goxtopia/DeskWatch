from PySide6.QtWidgets import QFrame, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

class DashboardPanel(QFrame):
    """
    Dashboard panel showing daily statistics fetched from the server.
    Marked as 'interactive' to block click-through.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardPanel")
        self.setProperty("interactive", True)
        self.setFrameShape(QFrame.NoFrame)
        
        self.setStyleSheet("""
            QFrame#DashboardPanel {
                background: rgba(255, 255, 255, 6);
                border-top: 1px solid rgba(255, 255, 255, 10);
                border-bottom: 1px solid rgba(255, 255, 255, 10);
            }
            QLabel {
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QLabel#Title {
                font-weight: bold;
                color: #ffffff;
                font-size: 12px;
            }
            QFrame.StatCard {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 10);
                border-radius: 6px;
            }
            QLabel.StatVal {
                font-weight: bold;
                font-size: 13px;
                color: #64B5F6;
            }
            QLabel.StatLabel {
                color: #aaaaaa;
                font-size: 9px;
            }
            QFrame#CompBar {
                background: #4FC3F7;
                border-radius: 2px;
            }
            QFrame#PhoneBar {
                background: #FFB74D;
                border-radius: 2px;
            }
            QFrame#EmptyBar {
                background: rgba(255, 255, 255, 30);
                border-radius: 2px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Header Title
        self.title_label = QLabel("📊 Daily Dashboard")
        self.title_label.setObjectName("Title")
        main_layout.addWidget(self.title_label)

        # Last Active Status
        self.last_active_label = QLabel("⏳ Time since last break: -")
        self.last_active_label.setObjectName("LastActiveStatus")
        self.last_active_label.setStyleSheet("""
            QLabel#LastActiveStatus {
                color: #FFE082;
                font-weight: bold;
                font-size: 10px;
                margin-top: -4px;
                margin-bottom: 2px;
            }
        """)
        main_layout.addWidget(self.last_active_label)

        # Stats Grid (2x2)
        grid_layout = QGridLayout()
        grid_layout.setSpacing(6)

        # 1. Total Tracked Time
        self.card_time = self._create_card("⏱️ Monitored", "0m", "#4DB6AC")
        grid_layout.addWidget(self.card_time, 0, 0)

        # 2. Overtime Sitting
        self.card_overtime = self._create_card("🪑 Overtime", "0m", "#E57373")
        grid_layout.addWidget(self.card_overtime, 0, 1)

        # 3. Valid Breaks
        self.card_breaks = self._create_card("🚶 Breaks", "0", "#81C784")
        grid_layout.addWidget(self.card_breaks, 1, 0)

        # 4. Water Drink Count
        self.card_water = self._create_card("🥛 Water Intake", "0", "#64B5F6")
        grid_layout.addWidget(self.card_water, 1, 1)

        main_layout.addLayout(grid_layout)

        # Ratio Breakdown Label
        ratio_header_layout = QHBoxLayout()
        ratio_header_layout.setContentsMargins(0, 4, 0, 0)
        ratio_header_layout.setAlignment(Qt.AlignVCenter)
        
        self.comp_label = QLabel("💻 Comp: -")
        self.comp_label.setStyleSheet("color: #4FC3F7; font-size: 10px; margin-bottom: 0px;")
        self.comp_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.phone_label = QLabel("📱 Phone: -")
        self.phone_label.setStyleSheet("color: #FFB74D; font-size: 10px; margin-bottom: 0px;")
        self.phone_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        ratio_header_layout.addWidget(self.comp_label)
        ratio_header_layout.addWidget(self.phone_label)
        main_layout.addLayout(ratio_header_layout)

        # Ratio dynamic progress bar
        self.ratio_bar_container = QFrame()
        self.ratio_bar_container.setFixedHeight(6)
        self.ratio_layout = QHBoxLayout(self.ratio_bar_container)
        self.ratio_layout.setContentsMargins(0, 0, 0, 0)
        self.ratio_layout.setSpacing(2)
        main_layout.addWidget(self.ratio_bar_container)

        self._setup_ratio_bar(0, 0)

        # Add vertical stretch to keep dashboard compact and prevent vertical misalignment
        main_layout.addStretch()

    def _create_card(self, label_text, val_text, val_color):
        card = QFrame()
        card.setObjectName("StatCard")
        card.setProperty("interactive", True)
        card.setFrameShape(QFrame.NoFrame)
        card.setStyleSheet("QFrame#StatCard { background: rgba(255, 255, 255, 10); border-radius: 6px; }")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        
        val_label = QLabel(val_text)
        val_label.setObjectName("Val")
        val_label.setProperty("interactive", True)
        val_label.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {val_color};")
        
        lbl = QLabel(label_text)
        lbl.setProperty("interactive", True)
        lbl.setStyleSheet("color: #aaaaaa; font-size: 9px;")
        
        layout.addWidget(val_label)
        layout.addWidget(lbl)
        
        # Attach reference for updates
        card.val_label = val_label
        return card

    def _setup_ratio_bar(self, comp_count, phone_count):
        # Clear layout
        while self.ratio_layout.count():
            item = self.ratio_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if comp_count == 0 and phone_count == 0:
            bar = QFrame()
            bar.setObjectName("EmptyBar")
            bar.setProperty("interactive", True)
            self.ratio_layout.addWidget(bar)
        else:
            if comp_count > 0:
                bar_comp = QFrame()
                bar_comp.setObjectName("CompBar")
                bar_comp.setProperty("interactive", True)
                self.ratio_layout.addWidget(bar_comp, stretch=comp_count)
            if phone_count > 0:
                bar_phone = QFrame()
                bar_phone.setObjectName("PhoneBar")
                bar_phone.setProperty("interactive", True)
                self.ratio_layout.addWidget(bar_phone, stretch=phone_count)

    def update_stats(self, data):
        """
        Updates UI text fields and graphs from statistical data dictionary.
        """
        # Read parameters with fallbacks
        total_time = data.get("total_time_str", "0m")
        overtime = data.get("overtime_minutes", 0)
        breaks = data.get("valid_breaks", 0)
        water = data.get("drinking_count", 0)
        comp_time = data.get("computer_time_str", "0m")
        phone_time = data.get("phone_time_str", "0m")

        # Update grid labels
        self.card_time.val_label.setText(str(total_time))
        self.card_overtime.val_label.setText(f"{overtime}m")
        self.card_breaks.val_label.setText(str(breaks))
        self.card_water.val_label.setText(str(water))

        # Update breakdown labels
        self.comp_label.setText(f"💻 Comp: {comp_time}")
        self.phone_label.setText(f"📱 Phone: {phone_time}")

        # Update ratios
        summary = data.get("summary", {})
        comp_count = summary.get("Using Computer", 0)
        phone_count = summary.get("Looking at Phone", 0)
        self._setup_ratio_bar(comp_count, phone_count)

    def update_inactive_time(self, inactive_minutes, is_sedentary=False):
        """
        Updates the 'Time since last break' indicator.
        """
        if inactive_minutes is None:
            self.last_active_label.setText("⏳ Time since last break: -")
        elif inactive_minutes == 0.0:
            self.last_active_label.setText("⏳ Time since last break: Currently on break")
        else:
            mins = int(inactive_minutes)
            secs = int((inactive_minutes - mins) * 60)
            if mins > 0:
                time_str = f"{mins}m {secs}s" if secs > 0 else f"{mins}m"
            else:
                time_str = f"{secs}s"
                
            if is_sedentary:
                self.last_active_label.setText(f"⏳ Time since last break: {time_str} (Sedentary ⚠️)")
            else:
                self.last_active_label.setText(f"⏳ Time since last break: {time_str}")
