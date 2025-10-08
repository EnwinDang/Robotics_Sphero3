import pygame
import time
import sys
from spherov2 import scanner
from spherov2.types import Color
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.commands.power import Power
import math

'''
SB-9DD8 1
SB-2BBE 2
SB-27A5 3
SB-81E0 4
SB-7740 5
'''

buttons = {
    '1': 0,
    '2': 1,
    '3': 2,
    '4': 3,
    'L1': 4,
    'L2': 6,
    'R1': 5,
    'R2': 7,
    'SELECT': 8,
    'START': 9
}



class SpheroController:
    def __init__(self, joystick, color, ball_number):
        self.toy = None
        self.speed = 50
        self.heading = 0
        self.base_heading = 0
        self.is_running = True
        self.calibration_mode = False
        self.joystick = joystick
        self.last_command_time = time.time()
        self.heading_reset_interval = 1
        self.last_heading_reset_time = time.time()
        self.threshold_accel_mag = 0.05
        self.collision_occurred = False
        self.color = color  # Store the color parameter
        self.previous_button = 1
        self.number = ball_number  # Assign the ball number
        self.gameStartTime = time.time()
        self.gameOn = False
        self.boosterCounter = 0
        self.calibrated = False

        # Analog vector control parameters
        self.deadzone = 0.15
        self.expo = 0.35  # 0=linear, higher makes center less sensitive
        self.max_speed = 255  # device max; presets scale within this
        self._last_sent_heading = None
        self._last_sent_speed = 0
        self._min_command_interval = 0.03  # ~33 Hz cap
        self._last_send = 0.0
        self._smooth_speed = 0.0
        self._smooth_alpha = 0.45  # smoothing factor

        

    def discover_nearest_toy(self):
        try:
            toys = scanner.find_toys()
            if not toys:
                print("Geen Sphero's gevonden.")
                return
            self.toy = toys[0]
            print(f"Dichtstbijzijnde Sphero toy '{self.toy.name}' ontdekt.")            
            return self.toy.name
        except Exception as e:
            print(f"Error no toys nearby: {e}")
        
    
    def discover_toy(self, toy_name):
        try:
            self.toy = scanner.find_toy(toy_name=toy_name)
            print(f"Sphero toy '{toy_name}' discovered.")
        except Exception as e:
            print(f"Error discovering toy: {e}")

    def connect_toy(self):
        if self.toy is not None:
            try:
                return SpheroEduAPI(self.toy)
            except Exception as e:
                print(f"Error connecting to toy: {e}")
        else:
            print("No toy discovered. Please run discover_toy() first.")
            return None

    def move(self, api, heading, speed):
        api.set_heading(heading)
        api.set_speed(speed)

    def _apply_deadzone_expo(self, value):
        # Apply circular deadzone/expo for joystick magnitude component [0..1]
        if value <= self.deadzone:
            return 0.0
        # Normalize to 0..1 after deadzone
        norm = (value - self.deadzone) / (1.0 - self.deadzone)
        if self.expo <= 0.0:
            return max(0.0, min(1.0, norm))
        # Exponential response curve
        curved = pow(norm, 1.0 + self.expo)
        return max(0.0, min(1.0, curved))

    def _compute_vector_command(self, X, Y, preset_speed):
        # Map joystick (X right+, Y down+) to heading and speed
        # We want forward (Y < 0) to be base_heading, right to be +90
        magnitude = math.sqrt(X * X + Y * Y)
        magnitude = min(1.0, magnitude)
        adj = self._apply_deadzone_expo(magnitude)
        if adj == 0.0:
            return None, 0

        angle_deg = math.degrees(math.atan2(X, -Y))  # 0 forward, +90 right
        heading = (self.base_heading + angle_deg) % 360

        # Scale speed by preset (0..max_speed)
        speed = int(max(0, min(self.max_speed, (preset_speed / self.max_speed) * self.max_speed * adj)))
        return heading, speed

    def _should_send(self, heading, speed):
        now = time.time()
        if now - self._last_send < self._min_command_interval:
            return False
        if self._last_sent_heading is None:
            return True
        dh = abs((heading - self._last_sent_heading + 180) % 360 - 180)
        ds = abs(speed - self._last_sent_speed)
        return dh >= 3 or ds >= 5

    def _send_command(self, api, heading, speed):
        if not self._should_send(heading, speed):
            return
        # Smooth speed to reduce wheel slip and packet bursts
        self._smooth_speed = (
            self._smooth_alpha * speed + (1.0 - self._smooth_alpha) * self._smooth_speed
        )
        self.move(api, heading, int(self._smooth_speed))
        self._last_sent_heading = heading
        self._last_sent_speed = int(self._smooth_speed)
        self._last_send = time.time()

    def toggle_calibration_mode(self, api, Y):
        if not self.calibration_mode:
            self.enter_calibration_mode(api, Y)
        else:
            self.exit_calibration_mode(api)

    def enter_calibration_mode(self, api, X):
        api.set_speed(0)
        self.gameStartTime = time.time()
        self.calibration_mode = True
        self.gameOn = False
        api.set_front_led(Color(255, 0, 0))

        self.base_heading = api.get_heading()

        if X < -0.7:
            new_heading = self.base_heading - 5
        elif X > 0.7:
            new_heading = self.base_heading + 5
        else:
            new_heading = self.base_heading

        api.set_heading(new_heading)

    def exit_calibration_mode(self, api):
        self.calibrated = True
        self.calibration_mode = False
        self.gameOn = True
        self.boosterCounter = 0
        self.gameStartTime = time.time()
        api.set_front_led(Color(0, 255, 0))
        # brief blink to signal calibrated
        try:
            api.set_main_led(Color(0, 60, 0))
            time.sleep(0.1)
            api.set_main_led(Color(0, 0, 0))
            time.sleep(0.05)
            api.set_main_led(self.color)
        except Exception:
            pass

    LED_PATTERNS = {
        1: '1',
        2: '2',
        3: '3',
        4: '4',
        5: '5'
    }

    def set_number(self, number):
        self.number = int(number)

    def display_number(self, api):
        number_char = self.LED_PATTERNS.get(self.number)
        if number_char:
            api.set_matrix_character(number_char, self.color)
        else:
            print(f"Error in matrix '{self.number}'")

    def print_battery_level(self, api):
        battery_voltage = Power.get_battery_voltage(self.toy)
        print(f"Battery status of {self.number}: {battery_voltage} V ")
        if (battery_voltage > 4.1):
            api.set_front_led(Color(r=0, g=255, b=0))
        if battery_voltage < 4.1 and battery_voltage > 3.9:
            api.set_front_led(Color(r=255, g=255, b=0))
        if battery_voltage < 3.9:
            api.set_front_led(Color(r=255, g=100, b=0))
        if battery_voltage < 3.7:
            api.set_front_led(Color(r=255, g=0, b=0))
        if battery_voltage < 3.5:
            exit("Battery")

    def control_toy(self):
        try:
            with self.connect_toy() as api:
                last_battery_print_time = time.time()
                self.set_number(self.number)
                self.display_number(api)
                self.enter_calibration_mode(api, 0)
                self.exit_calibration_mode(api)

                while self.is_running:
                    pygame.event.pump()
                    if not self.gameOn:
                        self.gameStartTime = time.time()                        
                    current_time2 = time.time()
                    gameTime = current_time2 - self.gameStartTime    

                    if current_time2 - last_battery_print_time >= 30:
                        self.print_battery_level(api)
                        last_battery_print_time = current_time2
                                                            
                    if self.gameOn:
                        acceleration_data = api.get_acceleration()
                        if acceleration_data is not None:
                            x_acc = acceleration_data['x']
                            z_acc = acceleration_data['z']
                            angle = math.degrees(math.atan2(x_acc, z_acc))

                            if abs(angle) >= 30:
                                hillCounter += 1
                                if hillCounter > 10:
                                    seconds = (current_time2 - self.gameStartTime)
                                    print(f"Player {self.number} going wild")
                            else:
                                hillCounter = 0
                        else:
                            print("Acceleration data is not available.")
                    
                    X = self.joystick.get_axis(0)
                    Y = self.joystick.get_axis(1)
                    #for i in range(self.joystick.get_numbuttons()):
                    #    button = self.joystick.get_button(i)
                    #    print(f"Button {i}: {button}")


                    if (self.joystick.get_button(buttons['1']) == 1):
                        self.speed = 120
                        self.color=Color(r=255, g=200, b=0)
                        self.display_number(api)
                    if (self.joystick.get_button(buttons['2']) == 1):
                        self.speed =170
                        self.color = Color(r=255, g=100, b=0)
                        self.display_number(api)

                    if (self.joystick.get_button(buttons['3']) == 1):
                        self.speed = 210
                        self.color = Color(r=255, g=50, b=0)
                        self.display_number(api)

                    if (self.joystick.get_button(buttons['4']) == 1):
                        self.speed = 240
                        self.color = Color(r=255, g=0, b=0)
                        self.display_number(api)

                    # Boost (R2) to full speed when held
                    boost = 1 if self.joystick.get_button(buttons['R2']) == 1 else 0

                    heading, speed = self._compute_vector_command(X, Y, self.max_speed if boost else self.speed)
                    if speed == 0:
                        # Stop only if we were moving to avoid flooding
                        if self._last_sent_speed != 0:
                            api.set_speed(0)
                            self._last_sent_speed = 0
                            self._last_sent_heading = heading if heading is not None else self._last_sent_heading
                            self._last_send = time.time()
                    else:
                        self._send_command(api, heading, speed)
   
                    # Only sample heading occasionally; avoid high-rate queries
                    if time.time() - self.last_heading_reset_time >= self.heading_reset_interval:
                        try:
                            self.base_heading = api.get_heading()
                        except Exception:
                            pass
                        self.last_heading_reset_time = time.time()

        finally:
            pygame.quit()

def main(toy_name=None, joystickID=0, playerID=1):
    pygame.init()
    pygame.joystick.init()

    num_joysticks = pygame.joystick.get_count()
    if num_joysticks == 0:
        print("No joysticks found.")
        return

    joystick = pygame.joystick.Joystick(joystickID)
    joystick.init()

    sphero_color = Color(255, 0, 0)
    sphero_controller = SpheroController(joystick, sphero_color, playerID)

    if toy_name is None:
        exit("No toy name provided")

    sphero_controller.discover_toy(toy_name)


    if sphero_controller.toy:
        sphero_controller.control_toy()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python script.py <toy_name> <joystickNumber 0-1> <player 1-5>")
        sys.exit(1)
    
    toy_name = sys.argv[1]
    joystick = int(sys.argv[2])
    playerid = int(sys.argv[3])
    print(f"Try to connect to: {toy_name} with number {joystick} for player {playerid}")
    
    main(toy_name, joystick, playerid)
