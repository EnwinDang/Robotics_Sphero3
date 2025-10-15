from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
import time

toy = scanner.find_toy(toy_name="SB-B72B")
with SpheroEduAPI(toy) as api:
    api.reset_locator()
    api.set_heading(0)
    api.roll(0, 60, 2.0)  # roule 2 s tout droit
    api.roll(0, 0, 0.1)
    loc = api.get_location()
    print("Locator:", loc)
