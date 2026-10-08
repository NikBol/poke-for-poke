from monitor import state as st
from monitor.adapters import webhallen as wh

SINCE = 1735689600  # 2025-01-01


def prod(name, web=0, release=1789531200, cat="Leksaker & Hobby/Samlarkortspel/Pokémon"):
    return {
        "id": abs(hash(name)) % 10**6,
        "name": name,
        "categoryTree": cat,
        "price": {"price": "999.00"},
        "release": {"timestamp": release},
        "stock": {"web": web},
    }


def test_filter_keeps_etb_bundle_and_30th_drops_accessories_and_old():
    data = {
        "products": [
            prod("Pokemon 30th Celebration Elite Trainer Box"),
            prod("Pokemon Booster Bundle ME3"),
            prod("Pokemon 30th Celebration Sleeves"),
            prod("Pokemon Card Sleeves Pikachu"),
            prod("Pokemon Old Elite Trainer Box", release=1600000000),
            prod("Pokemon Single Booster Pack"),
            prod("Lego Set", cat="Lego"),
        ]
    }
    names = [i.name for i in wh.parse_search(data, SINCE)]
    assert names == [
        "Pokemon 30th Celebration Elite Trainer Box",
        "Pokemon Booster Bundle ME3",
        "Pokemon 30th Celebration Sleeves",
    ]


def test_apply_detail_reads_level_and_stock():
    item = wh.WebhallenItem(1, "x", "u", 999.0, 0)
    wh.apply_detail(item, {"minimumRankLevel": 26, "isShippable": True, "stock": {"web": 5}, "saleLimit": {"maxQtyPerCustomer": 1}})
    assert (item.min_level, item.web_stock, item.max_qty, item.shippable) == (26, 5, 1, True)


def test_level_alert_sequence_26_17_9():
    prev = {}
    seq = [(5, 26, True), (5, 26, False), (5, 17, True), (5, 17, False), (5, 9, True), (5, 9, False)]
    for stock, level, expected in seq:
        assert st.level_alert(prev, stock, level, 999, None) is expected
        prev = {"buyable": stock > 0, "level": level}


def test_no_alert_when_out_of_stock_and_realert_after_restock():
    assert not st.level_alert({}, 0, 26, 999, None)
    assert st.level_alert({"buyable": False, "level": None}, 3, 26, 999, None)


def test_price_cap_blocks_alert():
    assert not st.level_alert({}, 5, 26, 2000, 1500)


def test_old_sets_and_non_cards_filtered_new_sets_kept():
    from monitor.filters import wanted_title as w

    assert w("Pokémon TCG - Scarlet & Violet 10 Destined Rivals Booster Display (36 Booster)")
    assert w("Pokemon Scarlet & Violet 8.5: Prismatic Evolutions Super Premium Collection")
    assert w("Pokemon Tcg Scarlet Violet 9 Journey Together Booster Display 36 Booster")
    assert w("Pokémon TCG - Phantasmal Flames Booster Display (36 Booster)")
    assert not w("Pokémon TCG - Scarlet & Violet 7: Stellar Crown Booster Display (36 Booster)")
    assert not w("Pokémon TCG - Scarlet & Violet 1 Booster Display (36 Booster)")
    assert not w("Pokémon TCG - Scarlet & Violet 8 Surging Sparks Booster Display (36 Booster)")
    assert not w("Pokémon TCG - Sword & Shield Brilliant Stars Booster Display")
    assert not w("Pokemon Funism Palmsize Wonders Vol 1 Mystery box Display (12st)")
    assert not w("Pokemon Center Tohoku Special Box")
    assert not w("Pokemon Tcg 30th Celebration Booster Box (20 boosters) (Japansk) (m6a)")


def test_watch_alerts_on_restock_and_new_listing_logic():
    assert st.should_alert("out_of_stock", "in_stock", 64.1, None)
    assert not st.should_alert("out_of_stock", "out_of_stock", 64.1, None)
