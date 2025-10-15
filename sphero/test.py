#!/usr/bin/env python3
import time, sys, argparse
from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.types import Color
from spherov2.commands import sensor as SensorCmd

LED_READY = Color(0,0,255)
LED_RUN   = Color(255,120,0)
LED_OK    = Color(0,255,0)
LED_ERR   = Color(255,0,0)

def find_toy(name_or_mac):
    for t in scanner.find_toys():
        if t.name == name_or_mac or getattr(t, "address", "") == name_or_mac:
            return t
    return None

def calibrate_zero(api):
    print("🔧 Calibration: oriente 0° vers l'avant (ligne droite), puis ENTER …")
    try: api.start_calibration()
    except: pass
    input()
    try: api.finish_calibration()
    except: api.set_heading(0)
    print("✅ 0° fixé.\n")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--speed", type=int, default=70)
    p.add_argument("--heading", type=int, default=0)
    args = p.parse_args()

    toy = find_toy(args.name)
    if toy is None:
        print(f"❌ BOLT '{args.name}' introuvable.")
        sys.exit(1)

    print(f"✅ Connecté à {toy.name}")
    try:
        with SpheroEduAPI(toy) as api:
            # 🔕 coupe les notifications de collision (fix crash)
            try: SensorCmd.disable_collision_detected_notify(api.toy)
            except: pass
            try: SensorCmd.configure_collision_detection(api.toy, enabled=False)
            except: pass

            api.set_stabilization(True)
            api.set_back_led(255)
            api.set_main_led(LED_READY)

            calibrate_zero(api)

            print("Prêt. ENTER pour démarrer, puis Ctrl+C pour arrêter et afficher le temps.")
            input()

            for k in (3,2,1):
                print(f"… {k}")
                api.set_main_led(Color(255,255,0)); time.sleep(0.25)
                api.set_main_led(Color(0,0,0));     time.sleep(0.35)

            print("🏁 GO")
            api.set_main_led(LED_RUN)
            t0 = time.perf_counter()

            # avance tout droit jusqu'au Ctrl+C
            while True:
                api.roll(args.heading % 360, max(10, min(100, args.speed)), 1.0)

    except KeyboardInterrupt:
        # Stop + chrono
        try:
            with SpheroEduAPI(toy) as api:
                api.roll(0,0,0.2); api.set_main_led(LED_OK)
        except Exception:
            pass
        try:
            elapsed = time.perf_counter() - t0
            print(f"\n⏱️ Temps mesuré: {elapsed:.3f} s")
        except:
            print("\n⛔ Arrêté.")
    except Exception as e:
        print(f"💥 Erreur: {e}")
        try:
            with SpheroEduAPI(toy) as api:
                api.roll(0,0,0.2); api.set_main_led(LED_ERR)
        except Exception:
            pass
        sys.exit(2)

if __name__ == "__main__":
    main()
