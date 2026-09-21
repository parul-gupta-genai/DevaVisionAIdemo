"""
SOW 2.7 "demonstrate test events" — a scripted scenario through the real
detector and the real incident machine.

Nobody stages a fight to commission a fight detector, and the /zones/{id}/test
probe answers only "would this alert", not "does the system behave sensibly
over time". This runs a 60-second scenario containing the four things a
loading bay actually produces, and prints what the module raised for each.
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.plugins.fight import service                       # noqa: E402

FPS, H = 14.0, 160.0
DT = 1.0 / FPS


def person(cx, cy=400, h=H):
    w = h * 0.4
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def phase_boxes(t, step):
    """The scenario, in wall-clock seconds."""
    if t < 10:                                  # two people walking together
        x = 150 + t * 0.9 * H
        return "two people walking", [(1, person(x)), (2, person(x + 0.8 * H))]
    if t < 20:                                  # standing, talking, gesturing
        return "standing and talking", [
            (1, person(500 + math.sin(step * 0.6) * 3)),
            (2, person(500 + 0.8 * H + math.sin(step * 0.5) * 3))]
    if t < 25:                                  # someone runs past
        return "someone running past", [
            (1, person(500)), (2, person(500 + 0.8 * H)),
            (3, person(50 + (t - 20) * 3.0 * H))]
    if t < 40:                                  # the scuffle
        a = 500 + math.sin(step * 2.6) * 0.28 * H + math.sin(step * 5.1) * 0.12 * H
        b = 500 + 0.6 * H + math.sin(step * 2.9 + 1) * 0.28 * H
        return "SCUFFLE", [
            (1, person(a, 400 + math.sin(step * 3.7) * 0.10 * H)),
            (2, person(b, 400 + math.sin(step * 4.1) * 0.10 * H))]
    if t < 50:                                  # broken up, standing apart
        return "separated, standing", [
            (1, person(350)), (2, person(350 + 2.5 * H))]
    return "gone", []                           # both walked away


def main():
    zones = []                                  # whole frame, default preset
    state = {}
    raised = []
    last_phase = None
    print("SOW 2.7 demonstration — 60s scenario, whole-frame, standard preset")
    print("(no zone configured, so the whole frame is watched)\n")
    print(f"{'t(s)':>6}  {'phase':<24} people  incident")
    for step in range(int(60 * FPS)):
        t = step * DT
        phase, boxes = phase_boxes(t, step)
        hits = service.evaluate("demo", boxes, zones, state, now=1000.0 + t)
        for h in hits:
            raised.append((t, h))
        if phase != last_phase or hits:
            note = ""
            for h in hits:
                note = f"<< {h.event_type}  score={h.score:.2f}"
                if h.event_type == service.FIGHT_CLEARED:
                    note += f"  ran {h.duration_sec:.0f}s"
            print(f"{t:6.1f}  {phase:<24} {len(boxes):^6} {note}")
            last_phase = phase

    print("\nWhat the module raised:")
    if not raised:
        print("  (nothing)")
    for t, h in raised:
        print(f"  t={t:5.1f}s  {h.event_type}")
        print(f"            {h.describe()}")
    print(f"\n  {service.ADVISORY_NOTICE}")


if __name__ == "__main__":
    main()
