from src.forecasting.intervals import bootstrap_prediction_intervals, in_sample_residuals


def _residuals_by_step(h_max=7, spread=10.0):
    # A symmetric, nonzero-variance residual pool at each step 1..h_max.
    return {h: [-spread, -spread / 2, 0.0, spread / 2, spread] for h in range(1, h_max + 1)}


def test_bounds_bracket_point_forecast():
    point = [100.0] * 10
    lower, upper = bootstrap_prediction_intervals(point, _residuals_by_step(), seed=1)
    for p, lo, hi in zip(point, lower, upper):
        assert lo <= p <= hi


def test_band_widens_beyond_backtest_horizon():
    point = [100.0] * 14
    lower, upper = bootstrap_prediction_intervals(point, _residuals_by_step(h_max=7), seed=1)
    widths = [u - l for l, u in zip(lower, upper)]
    # Steps 1..7 use the real per-step pool (no scaling); steps 8..14 scale by
    # sqrt(h/7), so width must trend upward past step 7, not flatten.
    assert widths[13] > widths[6]
    assert all(widths[i] <= widths[i + 1] + 1e-9 for i in range(6, 13))


def test_deterministic_given_same_seed():
    point = [50.0] * 5
    r1 = bootstrap_prediction_intervals(point, _residuals_by_step(), seed=42)
    r2 = bootstrap_prediction_intervals(point, _residuals_by_step(), seed=42)
    assert r1 == r2


def test_band_strictly_widens_vs_point_with_nonzero_variance_residuals():
    point = [200.0] * 3
    lower, upper = bootstrap_prediction_intervals(point, _residuals_by_step(h_max=3), seed=7)
    for p, lo, hi in zip(point, lower, upper):
        assert lo < p < hi  # strict: nonzero-variance pool must not collapse to a point


def test_no_residuals_at_all_returns_zero_width_band():
    point = [10.0, 20.0]
    lower, upper = bootstrap_prediction_intervals(point, {})
    assert lower == point
    assert upper == point


def test_in_sample_residuals_computation():
    assert in_sample_residuals([10.0, 20.0], [9.0, 22.0]) == [1.0, -2.0]
