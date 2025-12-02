import logging
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
        self.turns_per_layer = 45.0 # This should be updated from the controller's settings
        
        # --- Live Data ---
        self.current_servo_pos = self.servo_min_angle # Current position of the wire guide
        self.current_turns = 0
        self.target_turns = 8000
        self.winding_active = False 
        self.wire_positions = [] # Store X positions of each wire strand

    def reset_view(self):
        """Resets the live view for a new winding job."""
        self.current_turns = 0
        self.current_servo_pos = self.servo_min_angle # Reset servo position to the start
        self.wire_positions = [] # This will be populated in paintEvent
        self.update()

    def paintEvent(self, event):
        """This method is called whenever the widget needs to be redrawn."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Get widget dimensions
        w = self.width()
        h = self.height()
        
        # Clear background
        painter.fillRect(self.rect(), QColor("#333"))

        # --- Draw Bobbin (Cross-section view) ---
        bobbin_draw_width = w * 0.8
        bobbin_draw_height = h * 0.6 # Use more vertical space
        margin_x = (w - bobbin_draw_width) / 2
        # Position bobbin towards the bottom
        bobbin_bottom_y = h - 30 
        bobbin_top_y = bobbin_bottom_y - bobbin_draw_height
        
        # Draw the bobbin flatwork as a 'T' shape
        painter.setBrush(QColor("#654321")) # Brown color
        # Bottom flange
        bottom_flange_rect = QRectF(margin_x, bobbin_bottom_y, bobbin_draw_width, 5)
        painter.drawRect(bottom_flange_rect)
        # Top flange
        top_flange_rect = QRectF(margin_x, bobbin_top_y - 5, bobbin_draw_width, 5)
        painter.drawRect(top_flange_rect)

        # --- Calculate position ratio based on winding progress ---
        pos_ratio = 0.0
        if self.turns_per_layer > 0:
            # Determine the current layer and progress within that layer
            # The layer number determines the direction of travel
            num_layers = int(self.current_turns / self.turns_per_layer)
            turns_in_current_layer = self.current_turns % self.turns_per_layer
            layer_progress_ratio = turns_in_current_layer / self.turns_per_layer

            # On even layers (0, 2, ...), traverse left-to-right (0.0 -> 1.0)
            if num_layers % 2 == 0:
                    pos_ratio = layer_progress_ratio
            # On odd layers (1, 3, ...), traverse right-to-left (1.0 -> 0.0)
            else:
                pos_ratio = 1.0 - layer_progress_ratio
            #logging.debug(f"pos_ratio calc: turns={self.current_turns}, turns/layer={self.turns_per_layer:.1f}, layer={num_layers}, turns_in_layer={turns_in_current_layer:.1f}, layer_progress={layer_progress_ratio:.3f} -> pos_ratio={pos_ratio:.3f}")


        # --- Full X-Position Calculation Breakdown (for debugging) ---
        # This block is now outside the 'winding_active' check to show the initial state.
        # Step 1: Get the total width of the widget in pixels.
        #    w = self.width()
        #
        # Step 2: Define a drawing area for the bobbin that is 80% of the total width.
        #    bobbin_draw_width = w * 0.8
        #
        # Step 3: Calculate the horizontal margin to center the drawing area.
        #    margin_x = (w - bobbin_draw_width) / 2
        #
        # Step 4 & 5: The pos_ratio is now calculated based on turns per layer.
        #
        # Step 6: Calculate the final X position by scaling the ratio to the drawing area
        #         and adding the left margin.
        current_wire_x_pos_debug = margin_x + (pos_ratio * bobbin_draw_width)
        #logging.debug(f"X-POS DEBUG (Turn {self.current_turns}): [Step 1] w={w}px -> [Step 2] bobbin_draw_width={bobbin_draw_width:.2f}px -> [Step 3] margin_x={margin_x:.2f}px | [Step 5] pos_ratio={pos_ratio:.3f} -> [Step 6] current_x = {margin_x:.2f} + ({pos_ratio:.3f} * {bobbin_draw_width:.2f}) = {current_wire_x_pos_debug:.2f}px")

        # --- Draw Wire Buildup (Cross-section view) ---
        if self.winding_active and self.wire_diameter > 0:
                scaled_wire_width = (self.wire_diameter / self.bobbin_length) * bobbin_draw_width if self.bobbin_length > 0 else 0

                # The new wire position is directly under the guide
                current_wire_x_pos = margin_x + (pos_ratio * bobbin_draw_width)

                # Add a new wire if it's the first one, or if the guide has moved
                # at least one wire-width away from the last one.
                if not self.wire_positions or \
                   (abs(current_wire_x_pos - self.wire_positions[-1]) >= scaled_wire_width and scaled_wire_width > 0):
                    self.wire_positions.append(current_wire_x_pos)
                    #logging.debug(f"PaintEvent: Added new wire at x={current_wire_x_pos:.2f} (Turn: {self.current_turns}, Servo: {self.current_servo_pos:.2f}, Ratio: {pos_ratio:.3f})")

                # Draw all the wires that have been laid down so far
                painter.setPen(QPen(QColor("gold"), 1)) # Use a pen for drawing lines
                for wire_x_pos in self.wire_positions:
                    # Draw a full-height vertical line for each recorded wire position
                    painter.drawLine(int(wire_x_pos), int(bobbin_top_y), int(wire_x_pos), int(bobbin_bottom_y))



                # --- Draw Wire from Guide to Buildup ---
                guide_x = margin_x + (pos_ratio * bobbin_draw_width)
                wire_start_y = top_flange_rect.top() # Bottom of the guide area
                
                # Calculate the top of the current buildup
                # The wire should always connect to the bottom of the bobbin area
                wire_end_y = bobbin_bottom_y
                
                painter.setPen(QPen(QColor("gold"), 1))
                painter.drawLine(int(guide_x), int(wire_start_y), int(guide_x), int(wire_end_y))
                # logging.debug(f"PaintEvent: Drawing guide wire from ({guide_x:.2f}, {wire_start_y:.2f}) to ({guide_x:.2f}, {wire_end_y:.2f})")

        # --- Draw Wire Guide (Servo) ---
        # Map servo angle to a horizontal position
        guide_x = margin_x + (pos_ratio * bobbin_draw_width)
        
        painter.setPen(QPen(QColor("cyan"), 3))
        # Draw guide above the top flange
        guide_bottom_y = top_flange_rect.top()
        painter.drawLine(int(guide_x), 0, int(guide_x), int(guide_bottom_y))
        painter.drawEllipse(int(guide_x) - 5, int(guide_bottom_y) - 10, 10, 10)

        # --- Draw Dimensions ---
        painter.setPen(QColor("white"))
        
        # Bobbin Length (vertical dimension on the left)
        length_text = f"{self.bobbin_length:.1f} mm"
        length_line_x = margin_x - 10
        painter.drawLine(int(length_line_x), int(bobbin_top_y), int(length_line_x), int(bobbin_bottom_y))
        
        painter.save()
        # Center of the vertical line
        painter.translate(length_line_x - 5, bobbin_top_y + bobbin_draw_height / 2)
        painter.rotate(-90) # Rotate text to be vertical
        # Center the text on the new (0,0) origin
        painter.drawText(QRectF(0, 0, 100, 20).translated(-50, -15), Qt.AlignmentFlag.AlignCenter, length_text)
        painter.restore()

        # Bobbin Height (horizontal dimension at the bottom)
        height_text = f"{self.bobbin_height:.1f} mm"
        height_line_y = bobbin_bottom_y + 13
        painter.drawLine(int(margin_x), int(height_line_y), int(margin_x + bobbin_draw_width), int(height_line_y))

        # Center the text horizontally along the line
        text_rect = QRectF(margin_x, height_line_y + 2, bobbin_draw_width, 15)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, height_text)