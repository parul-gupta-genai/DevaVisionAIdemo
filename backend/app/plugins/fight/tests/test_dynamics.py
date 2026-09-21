"""
SOW 2.7 — the motion layer: what separates a fight from everything else two
people do near each other.

Fight detection has one failure mode that decides whether it survives on a
real site: it fires on ordinary human proximity. Two colleagues talking, a
handshake, a crowd at a turnstile, someone running for a bus — all of these
put people close together or make them move fast, and a detector built on
"close AND moving" calls every one of them a fight.

The tests below are written as those scenarios rather than as unit checks on
helper functions, because the scenarios are the specification.

Everything here works from tracked person boxes only. No pixels are read, so
this is cheap enough to run on every frame of a 25-camera wall.
"""

import math

import pytest

from app.plugins.fight import dynamics as dyn

FPS = 14.0
DT = 1.0 / FPS
H = 160.0          # a person ~160px tall in mux space


def box(cx, cy, h=H):
    w = h * 0.4
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def walk(start_x, y=400, speed_bh=0.9, n=40, h=H):
    """Someone walking in a straight line, in body-heights per second."""
    step = speed_bh * h * DT
    return [(i * DT, box(start_x + i * step, y, h)) for i in range(n)]


def stand(x, y=400, n=40, h=H, jitter=1.0):
    """Someone standing still, with the pixel jitter a tracker always has."""
    return [(i * DT, box(x + math.sin(i * 0.7) * jitter, y, h)) for i in range(n)]


def scuffle(x, y=400, n=40, h=H, amp=0.28):
    """
    Someone in a fight: lurching back and forth rather than travelling.
    The displacement reverses direction constantly, which is the signal.
    """
    out = []
    for i in range(n):
        dx = math.sin(i * 2.6) * amp * h + math.sin(i * 5.1) * 0.12 * h
        dy = math.sin(i * 3.7) * 0.10 * h
        out.append((i * DT, box(x + dx, y + dy, h)))
    return out


def feed(track_state, samples):
    """Pushes samples into a track's rolling window; returns final agitation."""
    value = 0.0
    for t, b in samples:
        value = dyn.update_track(track_state, b, t)
    return value


# ----------------------------------------------------------------------
# agitation: what one person is doing
# ----------------------------------------------------------------------
def test_standing_still_is_not_agitated():
    st = {}
    assert feed(st, stand(400)) < dyn.AGITATION_THRESHOLD


def test_walking_is_not_agitated():
    """The single most common thing a camera sees."""
    st = {}
    assert feed(st, walk(200)) < dyn.AGITATION_THRESHOLD


def test_running_in_a_straight_line_is_not_agitated():
    """
    Fast, but going somewhere. Speed alone must not read as violence or every
    person late for a shift is a fight.
    """
    st = {}
    assert feed(st, walk(100, speed_bh=3.0)) < dyn.AGITATION_THRESHOLD


def test_a_scuffle_is_agitated():
    st = {}
    assert feed(st, scuffle(400)) >= dyn.AGITATION_THRESHOLD


def test_agitation_is_scale_free():
    """
    The same struggle near and far from the camera must score the same, or a
    zone's threshold means something different at each end of the yard.
    """
    near, far = {}, {}
    a_near = feed(near, scuffle(400, h=300))
    a_far = feed(far, scuffle(400, h=70))
    assert abs(a_near - a_far) < 0.35 * max(a_near, a_far)


def test_agitation_needs_history_before_it_reports():
    st = {}
    assert dyn.update_track(st, box(400, 400), 0.0) == 0.0


def test_a_track_window_is_bounded():
    st = {}
    feed(st, scuffle(400, n=500))
    assert len(st.get("samples", [])) <= dyn.WINDOW_SAMPLES


def test_a_teleporting_track_id_does_not_register_as_violence():
    """
    Tracker id reuse: the box jumps across the frame between calls. That is a
    bookkeeping artefact, not a person moving at 40 body-heights a second.
    """
    st = {}
    value = 0.0
    for i in range(20):
        value = dyn.update_track(st, box(100 if i % 2 else 1100, 400), i * DT)
    assert value < dyn.AGITATION_THRESHOLD


# ----------------------------------------------------------------------
# separation: who is involved with whom
# ----------------------------------------------------------------------
def test_people_at_arms_length_count_as_engaged():
    assert dyn.separation(box(400, 400), box(400 + 0.7 * H, 400)) < dyn.ENGAGE_SEPARATION


def test_people_across_the_yard_are_not_engaged():
    assert dyn.separation(box(200, 400), box(1100, 400)) > dyn.ENGAGE_SEPARATION


def test_separation_is_measured_in_body_heights():
    """So the same gap means the same thing at both ends of the frame."""
    near = dyn.separation(box(400, 400, 300), box(400 + 0.7 * 300, 400, 300))
    far = dyn.separation(box(400, 400, 70), box(400 + 0.7 * 70, 400, 70))
    assert abs(near - far) < 0.05


def test_people_at_different_depths_are_not_engaged():
    """
    Two people one behind the other look adjacent in a flat image. Very
    different box heights mean very different distances from the camera, so
    they are not in contact however close their centres look.
    """
    assert dyn.separation(box(400, 400, 300), box(420, 400, 80)) > dyn.ENGAGE_SEPARATION


# ----------------------------------------------------------------------
# the scenarios that decide whether this is usable
# ----------------------------------------------------------------------
def run_pair(a_samples, b_samples):
    """Both tracks through the full per-frame evaluation; returns pair scores."""
    state = {}
    scores = []
    for (t, ba), (_, bb) in zip(a_samples, b_samples):
        scores.append(dyn.evaluate_pairs(
            state, [(1, ba), (2, bb)], t).get((1, 2), 0.0))
    return scores


def test_two_people_standing_and_talking_is_not_a_fight():
    assert max(run_pair(stand(400), stand(400 + 0.8 * H))) < dyn.FIGHT_THRESHOLD


def test_two_people_walking_past_each_other_is_not_a_fight():
    """Close for a moment, but both travelling steadily."""
    a = walk(200, speed_bh=1.0, n=40)
    b = [(t, box(1000 - (x[0] - 200), 400)) for (t, x) in
         [(t, [b[0], b[1], b[2], b[3]]) for t, b in a]]
    b = [(t, box(1000 - (i * 1.0 * H * DT), 400)) for i, (t, _) in enumerate(a)]
    assert max(run_pair(a, b)) < dyn.FIGHT_THRESHOLD


def test_one_person_thrashing_alone_is_not_a_fight():
    """A fight needs two. Somebody waving alone is not one."""
    assert max(run_pair(scuffle(300), stand(1100))) < dyn.FIGHT_THRESHOLD


def test_two_people_fighting_scores_as_a_fight():
    a = scuffle(400)
    b = scuffle(400 + 0.6 * H)
    assert max(run_pair(a, b)) >= dyn.FIGHT_THRESHOLD


def test_a_crowd_standing_close_together_is_not_a_fight():
    state = {}
    people = [(i, box(300 + i * 0.7 * H, 400)) for i in range(6)]
    worst = 0.0
    for step in range(30):
        t = step * DT
        jittered = [(tid, box(b[0] + H * 0.2 + math.sin(step * 0.5 + tid) * 2,
                              400)) for tid, b in people]
        worst = max([worst] + list(dyn.evaluate_pairs(state, jittered, t).values()))
    assert worst < dyn.FIGHT_THRESHOLD


def test_a_fight_inside_a_crowd_is_still_found():
    """The hard case: two people fighting among bystanders standing close by."""
    state = {}
    fighters_a, fighters_b = scuffle(500), scuffle(500 + 0.6 * H)
    best = 0.0
    for step, ((t, ba), (_, bb)) in enumerate(zip(fighters_a, fighters_b)):
        boxes = [(1, ba), (2, bb)]
        boxes += [(10 + i, box(200 + i * 0.7 * H, 400)) for i in range(4)]
        best = max([best] + list(dyn.evaluate_pairs(state, boxes, t).values()))
    assert best >= dyn.FIGHT_THRESHOLD


def test_evaluate_tolerates_an_empty_frame():
    assert dyn.evaluate_pairs({}, [], 0.0) == {}


def test_state_does_not_grow_without_bound():
    state = {}
    for step in range(200):
        boxes = [(step * 10 + i, box(100 + i * 50, 400)) for i in range(4)]
        dyn.evaluate_pairs(state, boxes, step * DT)
    assert len(state.get("tracks", {})) <= dyn.MAX_TRACKS
