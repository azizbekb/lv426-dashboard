from sheets import _parse_controls, _parse_dataset, parse_number


def control_rows():
    rows = [["" for _ in range(16)] for _ in range(34)]
    rows[0][0] = "WEYLAND-YUTANI // TEST"
    rows[2][0] = "SIMULATION WINDOW"
    rows[2][4] = "DISTRIBUTION"
    rows[2][8] = "DYNAMICS"
    rows[3][0:2] = ["Start date", "2026-01-01"]
    rows[4][0:2] = ["End date", "2026-01-10"]
    rows[5][0:2] = ["Days in range", "10"]
    rows[6][0:2] = ["Active mines", "2"]
    rows[3][4] = "Distribution"
    rows[3][8] = "Mine noise smoothing"
    rows[3][14] = "0.55"
    rows[4][4] = "Normal mean (× nominal)"
    rows[4][6] = "1.00"
    rows[4][8] = "Common noise smoothing"
    rows[4][14] = "0.80"
    rows[5][4] = "Normal std dev (×)"
    rows[5][6] = "0.18"
    rows[5][8] = "Common volatility (σ)"
    rows[5][14] = "0.10"
    rows[6][4] = "Uniform min (×)"
    rows[6][6] = "0.70"
    rows[6][8] = "Annual trend"
    rows[6][14] = "3.0%"
    rows[7][4] = "Uniform max (×)"
    rows[7][6] = "1.30"
    rows[7][8] = "Random seed"
    rows[7][14] = "20261027"
    rows[8][4] = "Active mean (×)"
    rows[8][6] = "1.00"
    rows[8][8] = "Base utilization"
    rows[8][14] = "85.0%"
    rows[9][4] = "Active std dev (×)"
    rows[9][6] = "0.18"
    rows[9][8] = "Model horizon (days)"
    rows[9][14] = "1,095"
    rows[10][0] = "MINE FLEET"
    rows[10][5] = "DAY-OF-WEEK"
    rows[10][8] = "EVENT CALENDAR"
    rows[11][0] = "Active"
    rows[11][1] = "Mine"
    rows[11][5] = "Day"
    rows[11][8] = "Event"
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for offset, (day, factor) in enumerate(zip(weekdays, [1.04, 1.06, 1.03, 1.0, 0.98, 0.92, 0.88])):
        rows[12 + offset][5] = day
        rows[12 + offset][6] = str(factor)
    rows[12][8] = "Xenomorph infestation"
    rows[12][9] = "2026-03-12"
    rows[12][10] = "14"
    rows[12][11] = "-35.0%"
    rows[12][12] = "100%"
    rows[12][13] = "0"
    for index in range(20):
        row = rows[12 + index]
        row[0] = "Yes" if index < 2 else "No"
        row[1] = f"Test Mine {index + 1}"
        row[2] = str(index + 1)
        row[3] = str(1000 + index * 10)
    return rows


def test_parse_number_formats():
    assert parse_number("1,234") == 1234
    assert parse_number("3.0%") == 0.03
    assert parse_number("") is None
    assert parse_number("bad", 7) == 7


def test_parse_controls_survives_blank_rows_and_missing_dropdown_value():
    controls = _parse_controls(control_rows())
    assert controls["window"]["start"] == "2026-01-01"
    assert controls["window"]["days"] == 10
    assert controls["distribution"]["type"] == "Normal"
    assert controls["distribution"]["normal_mean"] == 1.0
    assert controls["distribution"]["uniform_max"] == 1.3
    assert controls["dynamics"]["annual_trend"] == 0.03
    assert controls["dynamics"]["seed"] == 20261027
    assert controls["weekday_factors"]["Mon"] == 1.04
    assert len(controls["events"]) == 1
    assert controls["events"][0]["name"] == "Xenomorph infestation"
    assert len(controls["mines"]) == 20
    assert controls["mines"][0] == {
        "number": 1,
        "name": "Test Mine 1",
        "active": True,
        "capacity": 1000.0,
    }
    assert controls["mines"][-1]["active"] is False


def test_parse_dataset_maps_mine_names_and_values():
    controls = _parse_controls(control_rows())
    header = ["Date", "Total output", "7-day avg"] + [f"Mine {i}" for i in range(1, 21)]
    first = ["2026-01-01", "1,500", "1,500", "1,000", "500"] + ["0"] * 18
    second = ["2026-01-02", "1,600", "1,550", "1,100", "500"] + ["0"] * 18
    data_rows = [header, first, second]
    dataset = _parse_dataset(data_rows, controls)
    assert dataset["dates"] == ["2026-01-01", "2026-01-02"]
    assert dataset["total"] == [1500, 1600]
    assert dataset["mines"][0]["name"] == "Test Mine 1"
    assert dataset["mines"][0]["values"] == [1000, 1100]
    assert dataset["mines"][1]["active"] is True
    assert dataset["mines"][2]["active"] is False
