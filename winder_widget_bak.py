from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF

class WinderWidget(QWidget):
    """
    A custom widget to visualize the winder, bobbin, and wire.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)

        # --- Simulation Parameters ---
        self.bobbin_length = 60.0
        self.bobbin_height = 9.0
        self.wire_diameter = 0.063
        self.servo_min_angle = 70.0
        self.servo_max_angle = 100.0
        
        # --- Live Data ---
        self.current_servo_pos = self.servo_min_angle # Current position of the wire guide
        self.current_turns = 0
        self.target_turns = 8000
        self.winding_active = False

    def reset_view(self):
        """Resets the live view for a new winding job."""
        self.current_turns = 0
        self.winding_active = True
        self.update()

    def paintEvent(self, event):
        """This method is called whenever the widget needs to be redrawn."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get widget dimensions
        w = self.width()
        h = self.height()
        
        # Clear background
        painter.fillRect(self.rect(), QColor("#333"))

        # --- Draw Bobbin ---
        # Define bobbin geometry based on widget size
        bobbin_draw_width = w * 0.8
        bobbin_draw_height = h * 0.5
        margin_x = (w - bobbin_draw_width) / 2
        margin_y = (h - bobbin_draw_height) / 2
        
        bobbin_rect = QRectF(margin_x, margin_y, bobbin_draw_width, bobbin_draw_height)

        # Draw the bobbin flatwork
        painter.setBrush(QColor("#654321")) # Brown color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(bobbin_rect)

        # --- Draw Wire Buildup ---
        if self.winding_active and self.wire_diameter > 0:
            turns_per_layer = self.bobbin_length / self.wire_diameter
            if turns_per_layer > 0:
                num_layers = int(self.current_turns / turns_per_layer)
                
                painter.setBrush(QColor("gold"))
                
                # Draw full layers
                for i in range(num_layers):
                    layer_y = margin_y - ((i + 1) * self.wire_diameter * (h/self.bobbin_height))
                    layer_height = self.wire_diameter * (h/self.bobbin_height)
                    layer_rect = QRectF(margin_x, layer_y, bobbin_draw_width, layer_height)
                    painter.drawRect(layer_rect)

                # Draw current partial layer
                turns_in_current_layer = self.current_turns % turns_per_layer
                current_layer_width = (turns_in_current_layer / turns_per_layer) * bobbin_draw_width
                layer_y = margin_y - ((num_layers + 1) * self.wire_diameter * (h/self.bobbin_height))
                layer_height = self.wire_diameter * (h/self.bobbin_height)
                layer_rect = QRectF(margin_x, layer_y, current_layer_width, layer_height)
                painter.drawRect(layer_rect)


        # --- Draw Wire Guide (Servo) ---
        # Map servo angle to a horizontal position
        angle_range = self.servo_max_angle - self.servo_min_angle
        pos_ratio = (self.current_servo_pos - self.servo_min_angle) / angle_range if angle_range != 0 else 0
        guide_x = margin_x + (pos_ratio * bobbin_draw_width)
        
        painter.setPen(QPen(QColor("cyan"), 3))
        painter.drawLine(int(guide_x), 0, int(guide_x), int(margin_y))
        painter.drawEllipse(int(guide_x) - 5, int(margin_y) - 10, 10, 10)

        # --- Draw Dimensions ---
        painter.setPen(QColor("white"))
        # Bobbin length
        painter.drawLine(int(margin_x), int(margin_y + bobbin_draw_height + 5), int(margin_x + bobbin_draw_width), int(margin_y + bobbin_draw_height + 5))
        painter.drawText(int(margin_x), int(margin_y + bobbin_draw_height + 20), f"{self.bobbin_length} mm")
        # Bobbin height
        painter.drawLine(int(margin_x - 5), int(margin_y), int(margin_x - 5), int(margin_y + bobbin_draw_height))
        painter.drawText(int(margin_x - 40), int(margin_y + bobbin_draw_height/2), f"{self.bobbin_height} mm")