import numpy as np
import pytest

from alphadesk import dsl, ops, pit, stats, synth


@pytest.fixture(scope="module")
def panel():
    p = synth.make_market(n_assets=80, n_days=400, n_noise=2, seed=3)
    synth.add_leaky_field(p)
    return p


def test_compiles_and_evaluates(panel):
    s = dsl.compile_signal("cs_rank(ts_mean(quality, 5) - delay(flow, 2))", panel)
    v = s.evaluate(panel)
    assert v.shape == (panel.T, panel.N)
    assert np.nanmin(v) >= 0 and np.nanmax(v) <= 1


@pytest.mark.parametrize("bad", ["delay(quality, -1)", "__import__('os')", "quality.real", "'text'",
                                 "cs_rank(nope)", "ts_mean(quality, 2.5)", "3 + 4"])
def test_rejects(panel, bad):
    with pytest.raises(dsl.CompileError):
        dsl.compile_signal(bad, panel)


def test_future_field_needs_delay(panel):
    from alphadesk.panel import Field
    panel.add_field(Field("tomorrow", lambda r: r["ret"], known_at=1))
    with pytest.raises(dsl.LookAheadError):
        dsl.compile_signal("cs_rank(tomorrow)", panel)
    dsl.compile_signal("cs_rank(delay(tomorrow, 1))", panel)


@pytest.mark.parametrize("name", sorted(ops.OPERATORS))
def test_every_operator_is_point_in_time(name):
    fn, n_arr, n_num = ops.OPERATORS[name]
    nums = {0: (), 1: (7,), 2: (-1, 1)}[n_num]
    if name == "winsorize":
        nums = (0.05,)
    if name == "neutralize":
        fn = lambda x, g: ops.neutralize(x, np.abs(np.round(g * 2)))
    assert pit.shift_test_operator(fn, n_arr, nums)


def test_leaky_field_is_caught(panel):
    assert not pit.shift_test_field(panel, "insight")["ok"]
    assert pit.shift_test_field(panel, "quality")["ok"]


def test_rank_ic_matches_scipy():
    from scipy import stats as st
    rng = np.random.default_rng(0)
    x, y = rng.standard_normal((5, 40)), rng.standard_normal((5, 40))
    ic = stats.rowwise_rank_ic(x, y)
    assert np.allclose(ic, [st.spearmanr(x[i], y[i])[0] for i in range(5)])


def test_deflation_kills_the_best_of_noise():
    rng = np.random.default_rng(1)
    R = rng.normal(0, 0.01, (252, 500))
    best = R[:, np.argmax(R.mean(0) / R.std(0))]
    assert stats.deflated_sr(best, 1)["dsr"] > 0.95      # looks great alone
    assert stats.deflated_sr(best, 500)["dsr"] < 0.95    # not after 500 tries


def test_pbo_low_for_a_real_edge():
    rng = np.random.default_rng(2)
    M = rng.normal(0, 0.01, (1000, 10))
    M[:, 0] += 0.003
    assert stats.pbo_cscv(M)["pbo"] < 0.1
