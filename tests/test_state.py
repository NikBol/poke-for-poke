from monitor import state as st


def test_alert_only_on_transition_into_buyable():
    assert st.should_alert("out_of_stock", "in_stock", 100, None)
    assert st.should_alert(None, "in_stock", 100, None)
    assert not st.should_alert("in_stock", "in_stock", 100, None)
    assert not st.should_alert("in_stock", "out_of_stock", 100, None)


def test_price_cap():
    assert not st.should_alert("out_of_stock", "in_stock", 900, 600)
    assert st.should_alert("out_of_stock", "in_stock", 500, 600)


def test_preorder_counts_as_buyable():
    assert st.should_alert("out_of_stock", "preorder_available_for_you", None, None)
    assert not st.should_alert("in_stock", "preorder_available_for_you", None, None)


def test_stale_gap_alerts_once():
    now = 10_000
    assert st.stale_gap_minutes({"last_run_ts": now - 31 * 60, "alerted_stale": False}, now) == 31
    assert st.stale_gap_minutes({"last_run_ts": now - 31 * 60, "alerted_stale": True}, now) is None
    assert st.stale_gap_minutes({"last_run_ts": now - 6 * 60, "alerted_stale": False}, now) is None
    assert st.stale_gap_minutes({"last_run_ts": None, "alerted_stale": False}, now) is None
