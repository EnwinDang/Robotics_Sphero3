#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, time, argparse, math
from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.commands import sensor as SensorCmd  # désactiver collisions (bug connu)

# === Trajet (cm) & headings (°) — remplace si besoin ===
SEGMENTS_CM = [200, 200, 100, 100, 150, 100, 100, 200, 250]
HEADINGS    = [  0,   90, 180, 270, 180,  90, 180, 270,   0]

# === Paramètres de conduite ===
SPEED_MAIN      = 70     # vitesse % “croisière”
SPEED_NEAR      = 40     # vitesse % “approche” (derniers cm)
NEAR_CM         = 25.0   # à partir de cette distance restante, on ralentit
STOP_BLEED_CM   = 5.0    # marge pour compenser l’inertie (on stoppe un peu avant)
SLICE_S         = 0.15   # durée d’un “pas” de contrôle (boucle)
ACC_HIT_G       = 1.2    # seuil de pic d'accélération (approx) pour choc (fallback)
TIME_MARGIN     = 1.6    # si fallback temps, cap de sécurité = expected * TIME_MARGIN

def find_toy(name_or_mac: str):
    for t in scanner.find_toys():
        if t.name == name_or_mac or getattr(t, "address", "") == name_or_mac:
            return t
    return None

def calibrate_zero(api: SpheroEduAPI):
    print("Calibration: aligne 0° vers le 1er segment, puis ENTER …")
    try: api.start_calibration()
    except: pass
    input()
    try: api.finish_calibration()
    except: api.set_heading(0)

def has_locator(api: SpheroEduAPI) -> bool:
    try:
        loc = api.get_location()
        return isinstance(loc, dict) and "x" in loc and "y" in loc
    except:
        return False

def reset_locator(api: SpheroEduAPI):
    try:
        api.reset_locator()
    except:
        pass

def read_xy(api: SpheroEduAPI):
    try:
        loc = api.get_location()
        if isinstance(loc, dict):
            return float(loc.get("x", 0.0)), float(loc.get("y", 0.0))
    except:
        pass
    return None

def read_acc_mag(api: SpheroEduAPI):
    """Retourne la norme approx de l'accélération (en 'g' approx), sinon None."""
    try:
        a = api.get_acceleration()
        if isinstance(a, dict):
            x = float(a.get("x", 0.0)); y = float(a.get("y", 0.0)); z = float(a.get("z", 0.0))
            return math.sqrt(x*x + y*y + z*z)
    except:
        pass
    return None

def run_segment_by_locator(api, heading_deg: int, distance_cm: float):
    """Conduit en boucle jusqu'à parcourir 'distance_cm' (locator), avec ralentissement et marge anti-surplus."""
    # point de départ (0,0)
    reset_locator(api)
    api.set_heading(int(heading_deg) % 360)

    target = max(0.0, distance_cm - STOP_BLEED_CM)  # stoppe un peu avant
    t0 = time.perf_counter()

    while True:
        # distance parcourue
        xy = read_xy(api)
        d = 0.0
        if xy:
            d = math.hypot(xy[0], xy[1])

        remaining = target - d
        if remaining <= 0:
            break

        # vitesse: on ralentit sur la fin
        speed = SPEED_NEAR if remaining <= NEAR_CM else SPEED_MAIN
        api.roll(int(heading_deg) % 360, speed, SLICE_S)

        # detection choc (filet de sécurité)
        acc = read_acc_mag(api)
        if acc and acc >= ACC_HIT_G:
            # choc probable → stop
            break

        # petit cap anti-boucle infinie (au cas où locator bug)
        if time.perf_counter() - t0 > 20.0:  # 20s par segment, très large
            break

    # stop court
    api.roll(int(heading_deg) % 360, 0, 0.05)

def seconds_for_distance(dist_cm: float, cmps: float) -> float:
    return dist_cm / cmps if cmps > 0 else 0.0

def run_segment_fallback_time(api, heading_deg: int, distance_cm: float, cmps: float):
    """Fallback si pas de locator: durée estimée + cap sécurité + choc accel."""
    dur_est = seconds_for_distance(distance_cm, cmps)
    dur_cap = max(dur_est * TIME_MARGIN, dur_est + 1.0)
    api.set_heading(int(heading_deg) % 360)

    t0 = time.perf_counter()
    while True:
        api.roll(int(heading_deg) % 360, SPEED_MAIN, SLICE_S)
        # choc accel ?
        acc = read_acc_mag(api)
        if acc and acc >= ACC_HIT_G:
            break
        if time.perf_counter() - t0 >= dur_cap:
            break

    api.roll(int(heading_deg) % 360, 0, 0.05)

def run_lap(api: SpheroEduAPI, segments_cm, headings, cmps: float):
    locator_ok = has_locator(api)
    for hdg, dist in zip(headings, segments_cm):
        if locator_ok:
            run_segment_by_locator(api, hdg, dist)
        else:
            run_segment_fallback_time(api, hdg, dist, cmps)

def main():
    p = argparse.ArgumentParser(description="Sphero BOLT — multi-tours avec arrêt par distance (locator)")
    p.add_argument("--name", required=True, help="Nom/MAC BOLT (ex: SB-9DD8)")
    p.add_argument("--cmps", type=float, default=41.7, help="Vitesse cm/s (fallback temps)")
    p.add_argument("--laps", type=int, default=1, help="Nombre de tours")
    p.add_argument("--segments", type=str, default=",".join(str(x) for x in SEGMENTS_CM))
    p.add_argument("--headings", type=str,  default=",".join(str(x) for x in HEADINGS))
    args = p.parse_args()

    segments = [float(x) for x in args.segments.split(",") if x.strip()]
    headings = [int(x)   for x in args.headings.split(",")  if x.strip()]
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
            # évite le crash lié aux threads de collision
            try: SensorCmd.disable_collision_detected_notify(api.toy)
            except: pass
            try: SensorCmd.configure_collision_detection(api.toy, enabled=False)
            except: pass

            api.set_stabilization(True)
            calibrate_zero(api)

            t0 = time.perf_counter()
            for lap in range(1, args.laps + 1):
                print(f"Lap {lap}/{args.laps}")
                run_lap(api, segments, headings, args.cmps)
                # réaligner vers le 1er segment pour le tour suivant
                api.set_heading(headings[0] % 360)
                api.roll(headings[0] % 360, 0, 0.1)
            api.roll(0, 0, 0.2)
            t1 = time.perf_counter()
            print(f"Total: {t1 - t0:.3f} s for {args.laps} lap(s)")

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
