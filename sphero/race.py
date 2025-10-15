#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, time, argparse
from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.commands import sensor as SensorCmd  # pour désactiver les collisions

# === Trajet (tes valeurs) ===
SEGMENTS_CM = [200, 200, 100, 100, 150, 100, 100, 200, 250]
HEADINGS    = [  0,  90, 180, 270, 180,  90, 180, 270,   0]

# === Vitesse ===
SPEED_PCT_DEFAULT = 70
CM_PER_SEC_DEFAULT = 41.7  # mesuré: 5 m en 12 s

def find_toy(name_or_mac: str):
    for t in scanner.find_toys():
        if t.name == name_or_mac or getattr(t, "address", "") == name_or_mac:
            return t
    return None

def seconds_for_distance(dist_cm: float, cmps: float) -> float:
    return dist_cm / cmps if cmps > 0 else 0.0

def calibrate_zero(api: SpheroEduAPI):
    print("Calibration: oriente 0° vers le 1er segment, puis ENTER …")
    try: api.start_calibration()
    except: pass
    input()
    try: api.finish_calibration()
    except: api.set_heading(0)

def run_lap(api: SpheroEduAPI, segments_cm, headings, cmps: float, speed_pct: int):
    # départ visuel simple
    for k in (3,2,1):
        print(f"... {k}")
        time.sleep(0.5)
    print("GO")

    t0 = time.perf_counter()
    for hdg, dist in zip(headings, segments_cm):
        api.set_heading(int(hdg) % 360)
        dur = seconds_for_distance(dist, cmps)
        api.roll(int(hdg) % 360, max(10, min(100, speed_pct)), dur)
        # petit arrêt entre segments pour marquer la rotation
        api.roll(int(hdg) % 360, 0, 0.05)
    t1 = time.perf_counter()
    print(f"Lap time: {t1 - t0:.3f} s")

def main():
    p = argparse.ArgumentParser(description="Sphero BOLT — autonome minimal")
    p.add_argument("--name", required=True, help="Nom/MAC de la BOLT (ex: SB-9DD8)")
    p.add_argument("--speed", type=int, default=SPEED_PCT_DEFAULT, help="Vitesse % (0–100)")
    p.add_argument("--cmps", type=float, default=CM_PER_SEC_DEFAULT, help="Vitesse en cm/s")
    p.add_argument("--segments", type=str, default=",".join(str(x) for x in SEGMENTS_CM),
                   help="Segments en cm (séparés par des virgules)")
    p.add_argument("--headings", type=str, default=",".join(str(x) for x in HEADINGS),
                   help="Headings en degrés (séparés par des virgules)")
    args = p.parse_args()

    segments = [float(x) for x in args.segments.split(",") if x.strip()]
    headings = [int(x) for x in args.headings.split(",") if x.strip()]
    if len(segments) != len(headings):
        print("Segments et headings doivent avoir la même longueur.")
        sys.exit(2)

    toy = find_toy(args.name)
    if toy is None:
        print(f"NO BOLT '{args.name}'")
        sys.exit(1)

    print(f"Connected {toy.name}")
    try:
        with SpheroEduAPI(toy) as api:
            # important pour éviter le crash de thread collision rencontré plus tôt
            try: SensorCmd.disable_collision_detected_notify(api.toy)
            except: pass
            try: SensorCmd.configure_collision_detection(api.toy, enabled=False)
            except: pass

            calibrate_zero(api)
            run_lap(api, segments, headings, args.cmps, max(10, min(100, args.speed)))
    except KeyboardInterrupt:
        try:
            with SpheroEduAPI(toy) as api:
                api.roll(0, 0, 0.2)
        except:
            pass
        print("\nSTOPPED")
    except Exception as e:
        print(f"Error: {e}")
        try:
            with SpheroEduAPI(toy) as api:
                api.roll(0, 0, 0.2)
        except:
            pass
        sys.exit(2)

if __name__ == "__main__":
    main()