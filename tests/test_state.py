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


QUIET = {"start": "02:00", "end": "06:00", "timezone": "Europe/Stockholm"}


def ts(s):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromisoformat(s).replace(tzinfo=ZoneInfo("Europe/Stockholm")).timestamp()


def test_in_quiet_boundaries():
    assert st.in_quiet(ts("2026-10-08T02:00:00"), QUIET)
    assert st.in_quiet(ts("2026-10-08T05:59:00"), QUIET)
    assert not st.in_quiet(ts("2026-10-08T06:00:00"), QUIET)
    assert not st.in_quiet(ts("2026-10-08T01:59:00"), QUIET)
    assert not st.in_quiet(ts("2026-10-08T12:00:00"), QUIET)


def test_overnight_gap_does_not_trigger_stale_alert():
    state = {"last_run_ts": ts("2026-10-08T01:55:00"), "alerted_stale": False}
    assert st.stale_gap_minutes(state, ts("2026-10-08T06:00:00"), QUIET) is None
    # a real delay after the quiet window still alerts: 2h of quiet excluded from a 5h gap
    state = {"last_run_ts": ts("2026-10-08T01:55:00"), "alerted_stale": False}
    gap = st.stale_gap_minutes(state, ts("2026-10-08T06:40:00"), QUIET)
    assert gap == 45  # 4h45m total minus 4h quiet


def test_daytime_delay_still_alerts_with_quiet_configured():
    state = {"last_run_ts": ts("2026-10-08T10:00:00"), "alerted_stale": False}
    assert st.stale_gap_minutes(state, ts("2026-10-08T10:31:00"), QUIET) == 31


def test_due_respects_interval_with_slack():
    s = {}
    assert st.due(s, "k", 15, now=1000)  # never checked
    st.mark_checked(s, "k", now=1000)
    assert not st.due(s, "k", 15, now=1000 + 5 * 60)
    assert not st.due(s, "k", 15, now=1000 + 10 * 60)
    assert st.due(s, "k", 15, now=1000 + 14 * 60 + 30)  # 15 min minus 1 min slack
    assert st.due(s, "other", None, now=1000)  # no interval means every run
