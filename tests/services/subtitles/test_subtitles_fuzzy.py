from __future__ import annotations

import pytest

from anishift.services.subtitles.fuzzy import fall, nor, rise

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("x", "expected"),
    [(-5.0, 0.0), (10.0, 0.0), (12.5, 0.25), (15.0, 0.5), (20.0, 1.0), (99.0, 1.0)],
)
def test_rise_is_zero_up_to_a_linear_between_and_one_from_b(x: float, expected: float) -> None:
    assert rise(x, 10.0, 20.0) == pytest.approx(expected)


@pytest.mark.parametrize(("x", "expected"), [(9.9, 0.0), (10.0, 0.0), (10.001, 1.0), (11.0, 1.0)])
def test_rise_with_equal_bounds_steps_just_above_a(x: float, expected: float) -> None:
    assert rise(x, 10.0, 10.0) == expected


@pytest.mark.parametrize("x", [-5.0, 10.0, 12.5, 15.0, 20.0, 99.0])
def test_fall_is_the_complement_of_rise(x: float) -> None:
    assert fall(x, 10.0, 20.0) == pytest.approx(1.0 - rise(x, 10.0, 20.0))


def test_fall_is_one_up_to_a_and_zero_from_b() -> None:
    assert (fall(10.0, 10.0, 20.0), fall(15.0, 10.0, 20.0), fall(20.0, 10.0, 20.0)) == (1.0, 0.5, 0.0)


def test_nor_of_no_degrees_is_zero() -> None:
    assert nor() == 0.0


@pytest.mark.parametrize("degree", [0.0, 0.3, 1.0])
def test_nor_of_one_degree_is_that_degree(degree: float) -> None:
    assert nor(degree) == pytest.approx(degree)


def test_nor_lets_every_degree_add_without_passing_one() -> None:
    assert nor(0.5, 0.5) == pytest.approx(0.75)
    assert nor(0.2, 0.5, 0.0) == pytest.approx(0.6)
    assert nor(0.9, 1.0) == 1.0
