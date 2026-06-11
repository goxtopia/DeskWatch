import os
import time
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QPoint, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication

from windows_frontend.config import ClientConfigManager
from windows_frontend.api_client import APIPollThread
from windows_frontend.components.drag_handle import DragHandle
from windows_frontend.components.dashboard_panel import DashboardPanel
from windows_frontend.components.settings_panel import SettingsPanel
from windows_frontend.components.reminder_overlay import ReminderOverlay
from windows_frontend.components.animations import BouncingLabel, start_breathing, stop_breathing

# Windows Hit Test constants
HTTRANSPARENT = -1
HTCLIENT = 1
HTCAPTION = 2

class DeskWatchWidget(QWidget):
    """
    Main translucent, frameless floating widget.
    Implements Windows hit-testing (WM_NCHITTEST) for selective mouse click-through.
    """
    def __init__(self, config_manager: ClientConfigManager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        
        # UI State variables
        self.click_through_enabled = self.config.click_through
        self.current_state = "Offline"
        self.is_connected = False
        self.last_predicted_label = ""
        
        # Sedentary alert local states
        self.snoozed_until = None
        self.dismissed_active_session = False
        
        # Dimensions
        self.HEIGHT_COMPACT = 70
        self.HEIGHT_DASHBOARD = 260
        self.HEIGHT_SETTINGS = 250
        self.WIDGET_WIDTH = 260
        
        # Window attributes
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.SubWindow | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(self.WIDGET_WIDTH, self.HEIGHT_COMPACT)
        self.setMaximumSize(self.WIDGET_WIDTH, self.HEIGHT_COMPACT)
        
        self.init_ui()
        self.apply_initial_config()
        self.start_polling()

    def init_ui(self):
        # 1. Outer Layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 2. Translucent Border Container
        self.container = QFrame()
        self.container.setObjectName("MainContainer")
        
        # Premium dark glassmorphism stylesheet
        self.container.setStyleSheet("""
            QFrame#MainContainer {
                background: rgba(20, 20, 30, 220); /* Dark semi-transparent */
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 12px;
            }
            QPushButton.HeaderBtn {
                background: transparent;
                border: none;
                font-size: 12px;
                padding: 4px;
                border-radius: 4px;
            }
            QPushButton.HeaderBtn:hover {
                background: rgba(255, 255, 255, 18);
            }
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # 3. Add Drag Handle Component
        self.drag_handle = DragHandle()
        container_layout.addWidget(self.drag_handle)

        # 4. State Display Bar (StateBar)
        self.state_bar = QFrame()
        self.state_bar.setFixedHeight(44)
        state_layout = QHBoxLayout(self.state_bar)
        state_layout.setContentsMargins(12, 0, 12, 0)
        state_layout.setSpacing(8)

        # Status Connection Indicator Dot
        self.conn_dot = QFrame()
        self.conn_dot.setFixedSize(8, 8)
        self.conn_dot.setStyleSheet("background-color: #FF1744; border-radius: 4px;") # Red initially
        state_layout.addWidget(self.conn_dot)

        # Bouncing Status Emoji
        self.emoji_label = BouncingLabel("💤")
        self.emoji_label.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        state_layout.addWidget(self.emoji_label)

        # Status Text
        self.status_label = QLabel("Connecting...")
        self.status_label.setStyleSheet("""
            color: #ffffff;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        state_layout.addWidget(self.status_label)
        state_layout.addStretch()

        # Dashboard Expand Trigger Button
        self.btn_stats = QPushButton("📊")
        self.btn_stats.setObjectName("StatsBtn")
        self.btn_stats.setToolTip("View dashboard stats")
        self.btn_stats.setProperty("interactive", True)
        self.btn_stats.setCursor(Qt.PointingHandCursor)
        self.btn_stats.setFixedSize(24, 24)
        self.btn_stats.className = "HeaderBtn"
        self.btn_stats.setStyleSheet("""
            background: transparent; border: none; font-size: 12px; border-radius: 4px;
        """)
        # Add dynamic hover border highlight
        self.btn_stats.setStyleSheet("QPushButton:hover { background: rgba(255, 255, 255, 15); }")
        self.btn_stats.clicked.connect(self.toggle_dashboard)
        state_layout.addWidget(self.btn_stats)

        # Settings Trigger Button
        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.setToolTip("Open settings")
        self.btn_settings.setProperty("interactive", True)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setStyleSheet("QPushButton:hover { background: rgba(255, 255, 255, 15); }")
        self.btn_settings.clicked.connect(self.toggle_settings)
        state_layout.addWidget(self.btn_settings)

        container_layout.addWidget(self.state_bar)

        # 5. Collapsible Panels (Dashboard / Settings)
        self.dashboard_panel = DashboardPanel()
        self.dashboard_panel.setVisible(False)
        container_layout.addWidget(self.dashboard_panel)

        self.settings_panel = SettingsPanel(self.config)
        self.settings_panel.setVisible(False)
        container_layout.addWidget(self.settings_panel)

        outer_layout.addWidget(self.container)

        # 6. Sedentary Alert Overlay
        self.reminder_overlay = ReminderOverlay(self)
        self.reminder_overlay.setVisible(False)
        self.reminder_overlay.snooze_clicked.connect(self.snooze_alert)
        self.reminder_overlay.dismiss_clicked.connect(self.dismiss_alert)

        # Connect settings callbacks
        self.settings_panel.save_clicked.connect(self.save_settings)
        self.settings_panel.cancel_clicked.connect(self.toggle_settings)

    def apply_initial_config(self):
        # Apply Window Always on Top state
        self.set_always_on_top(self.config.always_on_top)
        
        # Position restoration
        x, y = self.config.window_position
        if x is not None and y is not None:
            self.move(x, y)
        else:
            screen_geom = QApplication.primaryScreen().geometry()
            # Position at top-right by default
            self.move(screen_geom.width() - self.WIDGET_WIDTH - 40, 60)

    def start_polling(self):
        self.poll_thread = APIPollThread(self.config, self)
        self.poll_thread.status_received.connect(self.handle_status_update)
        self.poll_thread.stats_received.connect(self.dashboard_panel.update_stats)
        self.poll_thread.connection_changed.connect(self.handle_connection_change)
        self.poll_thread.start()

    def set_always_on_top(self, on):
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # --- Panel Sliders & Geometry Animations ---
    
    def toggle_dashboard(self):
        # Collapse settings if showing
        if self.settings_panel.isVisible():
            self.settings_panel.setVisible(False)
            
        is_visible = self.dashboard_panel.isVisible()
        if not is_visible:
            self.dashboard_panel.setVisible(True)
            self.animate_height(self.HEIGHT_DASHBOARD)
            self.poll_thread.trigger_refresh()  # Pull stats immediately
        else:
            self.animate_height(self.HEIGHT_COMPACT)
            # Hide panel after animation concludes
            self.dashboard_panel.setVisible(False)

    def toggle_settings(self):
        # Collapse dashboard if showing
        if self.dashboard_panel.isVisible():
            self.dashboard_panel.setVisible(False)
            
        is_visible = self.settings_panel.isVisible()
        if not is_visible:
            self.settings_panel.setVisible(True)
            self.animate_height(self.HEIGHT_SETTINGS)
        else:
            self.animate_height(self.HEIGHT_COMPACT)
            self.settings_panel.setVisible(False)

    def animate_height(self, target_h):
        geom = self.geometry()
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setStartValue(geom)
        self.anim.setEndValue(QRect(geom.x(), geom.y(), self.WIDGET_WIDTH, target_h))
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        # Set max height constraints during transition to permit rendering sizes
        self.setMinimumHeight(min(geom.height(), target_h))
        self.setMaximumHeight(max(geom.height(), target_h))
        
        def on_finished():
            self.setMinimumHeight(target_h)
            self.setMaximumHeight(target_h)
            
        self.anim.finished.connect(on_finished)
        self.anim.start()

    # --- Settings Management ---
    
    def save_settings(self, server_url, always_on_top, click_through):
        # Update managers
        self.config.server_url = server_url
        self.config.always_on_top = always_on_top
        self.config.click_through = click_through
        
        # Sync widget behavior
        self.click_through_enabled = click_through
        self.set_always_on_top(always_on_top)
        
        # Refresh network calls
        self.poll_thread.trigger_refresh()
        
        # Collapse settings back
        self.toggle_settings()

    # --- API Communication / Status Callbacks ---
    
    def handle_connection_change(self, is_connected, error_message):
        self.is_connected = is_connected
        if is_connected:
            self.conn_dot.setStyleSheet("background-color: #00E676; border-radius: 4px;") # Neon green
            stop_breathing(self.conn_dot)
        else:
            self.conn_dot.setStyleSheet("background-color: #FF1744; border-radius: 4px;") # Neon red
            # Make dot blink/breathe to alert the user of offline status
            start_breathing(self.conn_dot, start_val=0.2, end_val=1.0, duration=1000)
            self.status_label.setText("Offline")
            self.emoji_label.setText("💤")

    def handle_status_update(self, data):
        """
        Processes camera and sedentary metrics from poll thread.
        """
        # 1. Update text state
        is_running = data.get("is_running", False)
        status_text = data.get("status", "Offline")
        last_pred = data.get("last_prediction")

        emoji_map = {
            "using computer": "💻",
            "looking at phone": "📱",
            "away": "🚶",
            "standing": "🧘",
            "napping": "🛏️",
            "drinking water": "🥛"
        }

        if is_running and last_pred:
            label = last_pred.get("label", "Active")
            confidence = last_pred.get("confidence", 0.0)
            
            # Map emoji
            emoji = emoji_map.get(label.lower(), "🎯")
            self.emoji_label.setText(emoji)
            
            # Text formatting
            self.status_label.setText(f"{label} ({int(confidence * 100)}%)")
            self.last_predicted_label = label
        else:
            self.emoji_label.setText("📷" if is_running else "💤")
            self.status_label.setText(status_text)
            self.last_predicted_label = ""

        # 2. Check sedentary warnings
        sedentary_status = data.get("sedentary_status")
        if sedentary_status:
            inactive_mins = sedentary_status.get("inactive_minutes", 0.0)
            is_sed = sedentary_status.get("is_sedentary", False)
            self.dashboard_panel.update_inactive_time(inactive_mins, is_sed)
            
            if is_sed:
                # We are sedentary!
                sedentary_mins = sedentary_status.get("sedentary_minutes", 0.0)
                self.trigger_sedentary_alert(sedentary_mins)
            else:
                self.clear_sedentary_alert()
        else:
            self.dashboard_panel.update_inactive_time(None)
            self.clear_sedentary_alert()

    def trigger_sedentary_alert(self, minutes):
        # Check snooze constraints
        if self.snoozed_until and time.time() < self.snoozed_until:
            return
        # Check dismissal constraints for this sitting session
        if self.dismissed_active_session:
            return
            
        # Display overlay and resize overlay to cover entire widget
        self.reminder_overlay.set_duration(minutes)
        self.reminder_overlay.setGeometry(self.rect())
        self.reminder_overlay.show()
        
        # Bring window to front
        self.raise_()
        self.activateWindow()

    def clear_sedentary_alert(self):
        # Hide overlay
        if self.reminder_overlay.isVisible():
            self.reminder_overlay.hide()
            
        # Reset session constraints since sitting session has been broken/reset
        self.dismissed_active_session = False
        self.snoozed_until = None

    def snooze_alert(self, minutes):
        self.snoozed_until = time.time() + (minutes * 60)
        self.reminder_overlay.hide()

    def dismiss_alert(self):
        self.dismissed_active_session = True
        self.reminder_overlay.hide()

    # --- Window Position Persistence & Resizing ---
    
    def moveEvent(self, event):
        super().moveEvent(event)
        # Persist coordinates
        pos = self.pos()
        self.config.set_window_position(pos.x(), pos.y())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep overlay locked to exact window size
        if self.reminder_overlay.isVisible():
            self.reminder_overlay.setGeometry(self.rect())

    # --- Hit Testing Override (WM_NCHITTEST) ---
    
    def is_over_interactive_widget(self, local_pos):
        """
        Finds QWidget at local position and checks if it or its ancestors block click-through.
        """
        widget = self.childAt(local_pos)
        while widget is not None:
            # Check property
            if widget.property("interactive") == True:
                return True
            # Check class
            if isinstance(widget, (QPushButton, QLineEdit, QCheckBox)):
                return True
            widget = widget.parentWidget()
        return False

    def is_over_drag_handle(self, local_pos):
        widget = self.childAt(local_pos)
        while widget is not None:
            if widget.property("drag_handle") == True:
                return True
            widget = widget.parentWidget()
        return False

    def nativeEvent(self, event_type, message):
        """
        Intercepts raw Windows OS messages.
        Specifically handles WM_NCHITTEST (0x0084) to determine cursor click-through states.
        """
        if event_type == b'windows_generic_MSG':
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                # Decode global mouse coordinates
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                # Convert unsigned 16-bit to signed integers
                if x >= 32768: x -= 65536
                if y >= 32768: y -= 65536
                
                global_pos = QPoint(x, y)
                local_pos = self.mapFromGlobal(global_pos)
                
                # 1. Drag handle check
                if self.is_over_drag_handle(local_pos):
                    # Return HTCAPTION (2) to let Windows drag the window
                    return True, HTCAPTION
                
                # 2. Click-through check
                if self.click_through_enabled:
                    if self.is_over_interactive_widget(local_pos):
                        # Return HTCLIENT (1) so the widget processes clicks normally
                        return True, HTCLIENT
                    else:
                        # Return HTTRANSPARENT (-1) so OS forwards clicks to windows behind
                        return True, HTTRANSPARENT
        return super().nativeEvent(event_type, message)

    # --- Close Gracefully ---
    
    def closeEvent(self, event):
        self.poll_thread.stop()
        self.poll_thread.wait()
        super().closeEvent(event)
