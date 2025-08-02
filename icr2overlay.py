from PyQt5.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QTimer
import sys, os, json
from icr2telemetry import ICR2Telemetry
from split_tracker import SplitTracker


def rotation_to_radians(raw_value):
    return (raw_value / 2147483648.0) * 3.141592653589793

def rotation_to_degrees(raw_value):
    return (raw_value / 2147483648.0) * 180.0

class ICR2Overlay(QWidget):
    def __init__(self):
        super().__init__()

        self.drag_pos = None
        self.setMouseTracking(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # Window appearance
        self.setWindowTitle("ICR2 Telemetry Overlay")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(100, 100, 350, 180)

        # Global stylesheet: label text color, background
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
            }
            QLabel {
                color: white;
                font-family: Consolas;
                font-size: 12pt;
            }
        """)

        # UI elements
        self.label = QLabel("", self)
        self.label.setTextFormat(Qt.RichText)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.reset_button = QPushButton("Reset Splits", self)
        self.toggle_json_button = QPushButton("", self)

        self.reset_button.clicked.connect(self.reset_splits)
        self.toggle_json_button.clicked.connect(self.toggle_json_output)

        # Button styling
        button_style = """
            QPushButton {
                color: white;
                background-color: #333333;
                border: 1px solid #888888;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """
        self.reset_button.setStyleSheet(button_style)
        self.toggle_json_button.setStyleSheet(button_style)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.toggle_json_button)
        self.setLayout(layout)

        # State
        self.split_tracker = SplitTracker(split1_dlong=24800000, split2_dlong=42000000)
        self.icr2 = ICR2Telemetry("rend32a")
        self.json_output_path = "telemetry_output.json"
        self.enable_json_output = True
        self.update_json_button_text()

        # Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_telemetry)
        self.timer.start(20)

    def reset_splits(self):
        self.split_tracker.reset()
        self.label.setText("Splits reset.")

    def toggle_json_output(self):
        self.enable_json_output = not self.enable_json_output
        self.update_json_button_text()
        status = "enabled" if self.enable_json_output else "disabled"
        self.label.setText(f"JSON output {status}.")

    def update_json_button_text(self):
        status = "ON" if self.enable_json_output else "OFF"
        self.toggle_json_button.setText(f"JSON Output: {status}")

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_R:
            self.reset_splits()

    def update_telemetry(self):
        try:
            session_time = self.icr2.get_session_time()
            minutes = session_time // 60000
            seconds = (session_time % 60000) / 1000

            durability = self.icr2.get_engine_durability()
            boost = self.icr2.get_boost()

            cars = self.icr2.get_cars_data()
            if len(cars) < 2:
                self.label.setText("Waiting for player car data...")
                return

            player = cars[1]
            f = player

            events = self.split_tracker.update(f['dlong'], session_time)

            line1 = (
                f"Time: {int(minutes):02}:{seconds:06.3f} | "
                f"Speed: {f['speed'] // 75:<3} | "
                f"DLONG: {f['dlong']:<8} | "
                f"DLAT: {f['dlat']:<8}"
            )
            line2 = (
                f"Rotation: {rotation_to_degrees(f['rotation']):0.1f} | "
                f"Steer angle: {f['steering'] / 11600000:0.1f} | "
            )
            line3 = (
                f"Durability: {durability / 9830400 * 100:6.2f}% | "
                f"Boost: {boost:5.2f} | "
            )
            line4_5 = self.split_tracker.formatted_summary()
            self.label.setText(f"{line1}<br>{line2}<br>{line3}<br>{line4_5}")

            if self.enable_json_output:
                output_data = {
                    "time_ms": session_time,
                    "speed_raw": f["speed"],
                    "speed_mph": f["speed"] / 75,
                    "dlong": f["dlong"],
                    "dlat": f["dlat"],
                    "rotation_deg": rotation_to_degrees(f["rotation"]),
                    "steering_raw": f["steering"],
                    "steering_deg": f["steering"] / 11600000,
                    "durability_raw": durability,
                    "durability_pct": durability / 9830400 * 100,
                    "boost": boost
                }
                with open(self.json_output_path, "w") as f_out:
                    json.dump(output_data, f_out)

        except Exception as e:
            self.label.setText(f"Error: {e}")

    def closeEvent(self, event):
        self.timer.stop()
        try:
            self.icr2.close()
        except Exception as e:
            print(f"Close failed: {e}")
        event.accept()
        os._exit(0)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ICR2Overlay()
    window.show()
    sys.exit(app.exec_())
