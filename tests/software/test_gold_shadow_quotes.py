from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from quant_service.gold_shadow_quotes import load_capture, parse_month


def source():
    return """Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh
        triệu đồng / lượng <table class="gv-table"><thead><tr>
        <th>Ngày</th><th>Mua lại</th><th>Bạn trả</th></tr></thead><tbody>
        <tr><td><a>22/11/2026</a> CN</td><td>130,0</td>
        <td><span>135,0</span><span>không đổi</span></td></tr>
        </tbody></table>""".encode()


def test_month_identity_units_and_sides():
    assert parse_month(source(), 2026, 11)["2026-11-22"] == dict(bid=130000000, ask=135000000, provider_carry_flag=True)
    for invalid in [source().replace(b'135,0', b'129,9'), source().replace('Mua lại'.encode(), b'sell'),
                    source().replace(b'1KG', b'rings'), source().replace(b'22/11', b'22/12'),
                    source().replace('không đổi'.encode(), b''), source().replace('không đổi'.encode(), b'unknown')]:
        with pytest.raises(ValueError):
            parse_month(invalid, 2026, 11)


def test_load_quote_only_from_verified_proposal_vintage(tmp_path, monkeypatch):
    raw = source()
    h = sha256(raw).hexdigest()
    rel = Path("refresh/full-phase1") / (h + ".json")
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_bytes(raw)
    stamp = "2026-11-24T09:15:00+00:00"
    receipt = dict(raw=dict(bytes=len(raw), sha256=h, file=rel.name, path=str(rel)),
                   url="https://giavang.tv/lich-su/2026/11", requested_at=stamp, received_at=stamp,
                   asset_id="GOLD", method="GET", status=200)
    day = date(2026, 11, 23)
    coverage = {"GOLD": dict(status="AVAILABLE", latest_observation_date="2026-11-23", raw_artifact_refs=[receipt])}
    panel = SimpleNamespace(snapshot=dict(created_at=stamp, asset_coverage=coverage), dates=[day], ids=["GOLD"],
                            prices=np.array([[135000000]]), valid=np.array([[True]]),
                            observation_days=np.array([[day.toordinal()-1]]),
                            known_seconds=np.array([[0]]), policy_seconds=np.array([[0]]))
    from quant_service import gold_shadow_quotes

    warmup = tmp_path / "warmup.csv"
    warmup.write_text("date,archive_bid,archive_ask,provider_carry_flag\n2026-04-30,130000,135000,False\n")
    monkeypatch.setattr(gold_shadow_quotes, "WARMUP_HASH", sha256(warmup.read_bytes()).hexdigest())
    args = (panel, day, datetime(2026, 11, 24, 10, tzinfo=timezone.utc), tmp_path, warmup)
    data = load_capture(*args)
    assert data["observed_quote"]["source_sha256"] == h and data["observed_quote"]["date"] == "2026-11-22"
    panel.prices[0, 0] = 1
    with pytest.raises(ValueError, match="disagree"):
        load_capture(*args)
    receipt["received_at"] = "2026-11-24T10:00:01+00:00"
    with pytest.raises(ValueError, match="cutoff"):
        load_capture(*args)
    receipt["received_at"] = stamp
    (tmp_path / rel).write_bytes(raw.replace(b'135,0', b'136,0'))
    with pytest.raises(ValueError, match="content changed"):
        load_capture(*args)
