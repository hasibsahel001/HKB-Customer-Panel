from app.services.vendors import load_table, lookup_vendor, normalize_prefix


def test_prefix_normalization():
    assert normalize_prefix("4c:5e:0c:11:22:33") == "4C:5E:0C"
    assert normalize_prefix("4C-5E-0C") == "4C:5E:0C"
    assert normalize_prefix("4c5e0c") == "4C:5E:0C"
    assert normalize_prefix("zz") is None
    assert normalize_prefix(None) is None


def test_builtin_and_unknown():
    assert lookup_vendor("4C:5E:0C:11:22:33") == "MikroTik"
    assert lookup_vendor("AA:BB:CC:11:22:33", table={}) is None
    assert lookup_vendor(None) is None


def test_csv_file_extends_the_table(tmp_path):
    path = tmp_path / "oui.csv"
    path.write_text("# comment\n\nAA:BB:CC,TP-Link\nddeeff , Tenda \nbad line\n", encoding="utf-8")
    table = load_table(path)
    assert lookup_vendor("aa:bb:cc:00:00:01", table=table) == "TP-Link"
    assert lookup_vendor("DD:EE:FF:00:00:01", table=table) == "Tenda"
    assert lookup_vendor("4C:5E:0C:00:00:01", table=table) == "MikroTik"


def test_missing_file_falls_back_to_the_builtin_table(tmp_path):
    assert lookup_vendor("4C:5E:0C:00:00:01", table=load_table(tmp_path / "none.csv")) == "MikroTik"