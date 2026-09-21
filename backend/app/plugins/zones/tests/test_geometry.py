"""
SOW 2.9 — Zone definition.

The client draws the area; these are the rules about what counts as a usable
drawing and what counts as being inside it.
"""

import pytest

from app.plugins.zones import geometry as g


# ----------------------------------------------------------------------
# The coordinate space
# ----------------------------------------------------------------------
def test_mux_space_matches_the_pipeline():
    """geometry.py duplicates MUX_W/H rather than importing; they must agree."""
    from config.config import MUX_H, MUX_W

    assert (g.MUX_W, g.MUX_H) == (MUX_W, MUX_H)


# ----------------------------------------------------------------------
# sanitize_polygon — shared by the API validator and the zone registry
# ----------------------------------------------------------------------
def test_accepts_a_plain_rectangle():
    assert g.sanitize_polygon([[10, 10], [200, 10], [200, 200], [10, 200]]) == \
        [[10, 10], [200, 10], [200, 200], [10, 200]]


def test_accepts_the_canvas_dict_form():
    assert g.sanitize_polygon(
        [{"x": 10, "y": 10}, {"x": 200, "y": 10}, {"x": 200, "y": 200}]
    ) == [[10, 10], [200, 10], [200, 200]]


def test_rejects_fewer_than_three_points():
    assert g.sanitize_polygon([[0, 0], [100, 100]]) is None


def test_rejects_more_than_the_point_cap():
    too_many = [[i, i * 2] for i in range(g.MAX_ZONE_POINTS + 1)]
    assert g.sanitize_polygon(too_many) is None


def test_rejects_a_misclick_sized_zone():
    """A few pixels across is a stray click, not an intent to monitor."""
    assert g.sanitize_polygon([[0, 0], [5, 0], [5, 5], [0, 5]]) is None


def test_rejects_collinear_points_with_no_area():
    assert g.sanitize_polygon([[0, 0], [50, 50], [100, 100]]) is None


def test_drops_drag_jitter_duplicates():
    poly = g.sanitize_polygon(
        [[10, 10], [10, 10], [200, 10], [200, 200], [10, 200]])
    assert poly == [[10, 10], [200, 10], [200, 200], [10, 200]]


def test_drops_a_closing_point_that_repeats_the_first():
    poly = g.sanitize_polygon(
        [[10, 10], [200, 10], [200, 200], [10, 200], [10, 10]])
    assert poly == [[10, 10], [200, 10], [200, 200], [10, 200]]


def test_clamps_points_to_the_mux_frame():
    poly = g.sanitize_polygon([[-50, -50], [5000, 0], [5000, 5000], [0, 5000]])
    assert poly == [[0, 0], [g.MUX_W, 0], [g.MUX_W, g.MUX_H], [0, g.MUX_H]]


@pytest.mark.parametrize("bad", [
    None, "polygon", 42,
    [[0, 0], [100, 0], [100, "x"]],
    [[0, 0], [100, 0], [100, None]],
    [{"x": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 2}],
])
def test_rejects_malformed_input(bad):
    assert g.sanitize_polygon(bad) is None


def test_rejects_booleans_masquerading_as_coordinates():
    """bool is an int in Python; a True coordinate is bad data, not x=1."""
    assert g.sanitize_polygon([[True, 0], [100, 0], [100, 100]]) is None


def test_polygon_area_is_orientation_independent():
    square = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert g.polygon_area(square) == 10000.0
    assert g.polygon_area(list(reversed(square))) == 10000.0


# ----------------------------------------------------------------------
# Containment
# ----------------------------------------------------------------------
SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]


def test_point_inside_and_outside():
    assert g.point_in_polygon(200, 200, SQUARE) is True
    assert g.point_in_polygon(50, 200, SQUARE) is False
    assert g.point_in_polygon(200, 500, SQUARE) is False


def test_a_point_on_the_edge_counts_as_inside():
    """
    A zone drawn along a wall puts a passer-by exactly on the edge for frames
    at a time; a strict test makes the alert flicker.
    """
    assert g.point_in_polygon(100, 200, SQUARE) is True   # on the left edge
    assert g.point_in_polygon(200, 300, SQUARE) is True   # on the bottom edge
    assert g.point_in_polygon(100, 100, SQUARE) is True   # on a vertex


def test_concave_polygon_notch_is_outside():
    """An L shape must not report the missing corner as inside."""
    L = [[0, 0], [300, 0], [300, 100], [100, 100], [100, 300], [0, 300]]
    assert g.point_in_polygon(50, 50, L) is True
    assert g.point_in_polygon(200, 200, L) is False       # the notch


def test_degenerate_polygon_contains_nothing():
    assert g.point_in_polygon(10, 10, [[0, 0], [1, 1]]) is False


# ----------------------------------------------------------------------
# Anchors — which part of a detection has to be inside
# ----------------------------------------------------------------------
def test_feet_is_the_bottom_centre_and_the_default():
    assert g.anchor_point([100, 0, 200, 400]) == (150.0, 400.0)
    assert g.anchor_point([100, 0, 200, 400], "FEET") == (150.0, 400.0)


def test_center_and_head_anchors():
    assert g.anchor_point([100, 0, 200, 400], "CENTER") == (150.0, 200.0)
    assert g.anchor_point([100, 0, 200, 400], "HEAD") == (150.0, 0.0)


def test_anchor_normalises_an_inverted_box():
    assert g.anchor_point([200, 400, 100, 0], "HEAD") == (150.0, 0.0)


def test_feet_anchor_ignores_someone_leaning_over_the_zone():
    """
    Standing outside with head and shoulders over the line is not being in
    the zone — that is the whole reason FEET is the default.
    """
    leaning = [150, 50, 250, 350]       # feet at y=350, below the square
    assert g.detection_in_zone(leaning, SQUARE, "FEET") is False
    assert g.detection_in_zone(leaning, SQUARE, "CENTER") is True


def test_box_anchor_catches_any_overlap():
    leaning = [150, 50, 250, 350]
    assert g.detection_in_zone(leaning, SQUARE, "BOX") is True


def test_box_overlap_with_no_corner_or_vertex_inside():
    """
    A wide zone band crossed by a tall person box: no box corner is in the
    polygon and no polygon vertex is in the box, so edge intersection is the
    only thing that catches it. This is the 'walked through the doorway' case.
    """
    band = [[0, 150], [400, 150], [400, 200], [0, 200]]
    tall = [180, 0, 220, 400]
    assert not any(g.point_in_polygon(cx, cy, band) for cx, cy in
                   [(180, 0), (220, 0), (220, 400), (180, 400)])
    assert g.bbox_overlaps_polygon(tall, band) is True


def test_box_overlap_rejects_a_clearly_separate_box():
    assert g.bbox_overlaps_polygon([500, 500, 600, 600], SQUARE) is False


def test_detection_in_zone_needs_a_real_polygon():
    assert g.detection_in_zone([100, 100, 200, 200], [[0, 0], [1, 1]]) is False
    assert g.detection_in_zone([100, 100, 200, 200], []) is False


def test_box_height_handles_inverted_boxes():
    assert g.box_height([0, 100, 10, 400]) == 300.0
    assert g.box_height([0, 400, 10, 100]) == 300.0
