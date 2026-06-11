from PySide6.QtWidgets import QWidget, QLabel, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QPropertyAnimation, QVariantAnimation, QEasingCurve, QPoint

class BouncingLabel(QWidget):
    """
    A layout-safe QWidget subclass that bounces its text/emoji.
    It encapsulates a QLabel and animates its position relative to the container,
    avoiding paint-device and QPainter conflicts.
    """
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        
        self.label = QLabel(text, self)
        self.label.setFixedSize(28, 28)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent; border: none;")
        
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0)
        self.anim.setKeyValueAt(0.5, -6)  # Bounces 6 pixels up
        self.anim.setEndValue(0)
        self.anim.setDuration(1200)       # 1.2 second cycle
        self.anim.setLoopCount(-1)        # Infinite loop
        self.anim.valueChanged.connect(self._set_offset)
        self.anim.start()

    def _set_offset(self, val):
        self.label.move(0, int(val))

    def setText(self, text):
        self.label.setText(text)

    def setStyleSheet(self, style):
        self.label.setStyleSheet(style)


def start_breathing(widget, start_val=0.3, end_val=1.0, duration=1200):
    """
    Applies a breathing opacity effect to any QWidget.
    """
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setStartValue(start_val)
    anim.setEndValue(end_val)
    anim.setDuration(duration)
    anim.setLoopCount(-1)
    anim.setEasingCurve(QEasingCurve.InOutQuad)
    anim.start()
    
    # Store references on the widget to prevent GC reclamation
    widget._breathing_anim = anim
    widget._breathing_effect = effect
    return anim


def stop_breathing(widget):
    """
    Removes the breathing animation and restores full opacity.
    """
    if hasattr(widget, "_breathing_anim"):
        widget._breathing_anim.stop()
        del widget._breathing_anim
    if hasattr(widget, "_breathing_effect"):
        widget.setGraphicsEffect(None)
        del widget._breathing_effect


def animate_window_height(window, start_h, end_h, duration=300):
    """
    Smoothly transitions the height of the main floating window.
    """
    # Animate minimumHeight and maximumHeight together to resize the frameless window
    anim_min = QPropertyAnimation(window, b"minimumHeight")
    anim_min.setStartValue(start_h)
    anim_min.setEndValue(end_h)
    anim_min.setDuration(duration)
    anim_min.setEasingCurve(QEasingCurve.InOutQuad)

    anim_max = QPropertyAnimation(window, b"maximumHeight")
    anim_max.setStartValue(start_h)
    anim_max.setEndValue(end_h)
    anim_max.setDuration(duration)
    anim_max.setEasingCurve(QEasingCurve.InOutQuad)

    anim_min.start()
    anim_max.start()

    window._height_anim_min = anim_min
    window._height_anim_max = anim_max
