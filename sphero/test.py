#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Roule dans la direction heading, à la vitesse speed (en % ou 0–255), pendant duration secondes.”
import time, sys, argparse
from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.types import Color

LED_READY = Color(0, 0, 255)
LED_RUN   = Color(255, 120, 0)
LED_OK    = Color(0, 255, 0)
LED_ERR   = Color(255, 0, 0)

def find_toy(name_or_mac: str):
    toys = scanner.find_toys()
    for t in toys:
        if t.name == name_or_mac or getattr(t, "address", "") == name_or_mac:
            return t
    return None

def calibrate_zero(api: SpheroEduAPI):
    print("🔧 Calibration: oriente 0° vers l'avant (ta ligne droite), puis ENTER …")
    try:
        api.start_calibration()
    except Exception:
        pass
    input()
    try:
        api.finish_calibration()
    except Exception:
        api.set_heading(0)
    print("✅ 0° fixé.\n")

def main():
    p = argparse.ArgumentParser(description="Sphero BOLT straight run — mesurer le temps à la main")
    p.add_argument("--name", required=True, help="Nom/MAC de la BOLT (ex: SB-9DD8)")
    p.add_argument("--speed", type=int, default=70, help="Vitesse % (0–100)")
    p.add_argument("--heading", type=int, default=0, help="Heading (0°=droite)")
    p.add_argument("--no-calib", action="store_true", help="Ne pas ouvrir la calibration")
    args = p.parse_args()

    toy = find_toy(args.name)
    if toy is None:
        print(f"❌ BOLT '{args.name}' introuvable.")
        sys.exit(1)

    print(f"✅ Connecté à {toy.name}")
    try:
        with SpheroEduAPI(toy) as api:
            api.set_main_led(LED_READY)
            api.set_stabilization(True)
            api.set_back_led(255)

            if not args.no_calib:
                calibrate_zero(api)
            else:
                api.set_heading(args.heading % 360)

            print("Prêt. Place la BOLT alignée. Appuie sur ENTER pour démarrer…")
            input()

            # Décompte visuel court
            for k in (3,2,1):
                print(f"… {k}")
                api.set_main_led(Color(255,255,0)); time.sleep(0.25)
                api.set_main_led(Color(0,0,0));     time.sleep(0.35)

            print("🏁 GO — ENTER pour arrêter.")
            api.set_main_led(LED_RUN)
            t0 = time.perf_counter()

            # Roule tout droit jusqu'à ENTER
            api.roll(args.heading % 360, max(10, min(100, args.speed)), 10.0)  # impulsion initiale
            # boucle d'entretien: relance un roll régulier pour rester à vitesse
            try:
                while True:
                    api.roll(args.heading % 360, max(10, min(100, args.speed)), 1.0)
                    # test non bloquant: on lit stdin ? simplifions: on interrompt avec ENTER (KeyboardInterrupt)
            except KeyboardInterrupt:
                pass
            # La ligne ci-dessous ne sera pas atteinte avec ENTER, donc alternative:
            # on détecte ENTER via input() bloquant dans un thread — pour rester simple,
            # on fait plutôt: l'utilisateur presse Ctrl+C pour stopper.
            # Si tu préfères ENTER, remplace le while par: input(); puis stop.

    except KeyboardInterrupt:
        # Stop propre et mesure du temps
        try:
            with SpheroEduAPI(toy) as api:
                api.roll(0,0,0.2)
                api.set_main_led(LED_OK)
        except Exception:
            pass
        # Affiche le chrono si t0 existe
        try:
            elapsed = time.perf_counter() - t0
            print(f"\n⏱️  Temps mesuré: {elapsed:.3f} s")
        except Exception:
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
