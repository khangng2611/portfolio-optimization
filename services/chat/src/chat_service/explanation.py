"""Finite Vietnamese claims grounded in frozen run evidence and canonical facts."""

import unicodedata
import re
from typing import Literal

from pydantic import Field
from portfolio_contracts import StrictModel, canonical_hash
from portfolio_contracts.explanation import RecommendationEvidence
from portfolio_contracts.assets import EQUITY_IDS


class ExplanationClaim(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_]{1,64}$")
    group: Literal["profile", "regime", "selection", "views", "features", "limitations"]
    template_id: str
    text: str = Field(max_length=2000)
    refs: list[str] = Field(min_length=1, max_length=8)


class ClaimPlan(StrictModel):
    facts_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_claim_ids: list[str] = Field(min_length=1, max_length=8)


def percent(value):
    return f"{float(value) * 100:.2f}".replace(".", ",") + "%"


def plain(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
        if not unicodedata.combining(c)
    )


def build_claims(facts, evidence):
    e = RecommendationEvidence.model_validate(evidence).checked()
    if (
        e.facts_hash != canonical_hash(facts)
        or e.recommendation_id != facts["id"]
        or e.run_id != facts.get("run_id")
    ):
        raise ValueError("Evidence does not belong to canonical recommendation")
    q = e.quant
    if q and (
        q.asset_ids != facts["asset_ids"]
        or q.input_hash != facts["input_hash"]
        or q.bundle_hash != facts["bundle_hash"]
        or q.snapshot_id != facts["data_snapshot_id"]
        or q.run_id != e.run_id
    ):
        raise ValueError("Quant evidence pins mismatch")
    claims = []

    def add(identity, group, text, refs):
        claims.append(
            ExplanationClaim(
                id=identity,
                group=group,
                template_id=group + "-v1",
                text=text,
                refs=refs,
            )
        )

    profile = facts.get("risk_profile") or {}
    labels = {
        "conservative": "Thận trọng",
        "balanced": "Cân bằng",
        "growth": "Tăng trưởng",
    }
    constraints = facts.get("constraints") or {}
    if profile.get("profile") in labels:
        text = "Hồ sơ đã ghim: " + labels[profile["profile"]] + "."
        answers = profile.get("answers") or {}
        if answers.get("horizon_months") is not None:
            text += f" Thời hạn trong hồ sơ là {int(answers['horizon_months'])} tháng; dự báo ML có kỳ hạn riêng."
        if constraints.get("risk_aversion") is not None:
            text += f" Hệ số ngại rủi ro được dùng: {float(constraints['risk_aversion']):g}."
        if constraints.get("max_non_defensive_weight") is not None:
            lower = max(
                float(constraints.get("min_defensive_weight", 0)),
                1 - float(constraints["max_non_defensive_weight"]),
            )
            text += f" Nhóm phòng thủ tối thiểu hiệu lực {percent(lower)}, kết hợp giới hạn ngoài nhóm phòng thủ và mức tối thiểu riêng."
        if constraints.get("max_position_weight") is not None:
            text += (
                " Mỗi tài sản tối đa "
                + percent(constraints["max_position_weight"])
                + "."
            )
        add("profile", "profile", text, ["facts.risk_profile", "facts.constraints"])
    else:
        add(
            "profile",
            "profile",
            "Đề xuất này chưa lưu đầy đủ hồ sơ khảo sát; chỉ có thể đối chiếu các giới hạn đã ghim.",
            ["facts.risk_profile", "facts.constraints"],
        )

    regime = (
        q.regime.model_dump()
        if q and q.regime
        else (facts.get("selection_context") or {}).get("regime")
    )
    if regime:
        state = {
            "normal": "bình thường",
            "stress": "căng thẳng",
            "crisis": "khủng hoảng",
        }[regime["regime"]]
        text = f"Rổ tài sản đang xét ở trạng thái {state} tại lần tính này. Tỷ lệ biến động cửa sổ 20/120 phiên: {regime['vol_ratio']:.2f}; drawdown cuối cửa sổ so với đỉnh trong cửa sổ 60 phiên: {percent(regime['drawdown'])}. Trung bình lợi suất ngày của rổ trong cửa sổ 60 phiên: {percent(regime['equity_momentum'])}."
        add(
            "regime",
            "regime",
            text,
            ["quant.regime"] if q and q.regime else ["facts.selection_context.regime"],
        )
    else:
        add(
            "regime",
            "regime",
            "Chưa lưu chỉ báo trạng thái rổ cho lần tính này; không bổ sung nhận định thị trường hiện tại vào kết quả cũ.",
            ["facts.diagnostics"],
        )

    proof = facts.get("selection_proof") or {}
    strategy = facts.get("strategy")
    active = proof.get("active_asset_ids") or (
        q.active_asset_ids if q else facts["asset_ids"]
    )
    if not proof.get("active_asset_ids") and q is None:
        active = ((facts.get("inputs_provenance") or {}).get("phase1_full") or {}).get(
            "active_asset_ids"
        ) or active
    if strategy == "HYBRID":
        active = facts["asset_ids"]
    weights = dict(zip(facts["asset_ids"], facts["weights"], strict=True))
    positive = [a for a in active if float(weights[a]) > 0]
    zero = [a for a in active if float(weights[a]) == 0]
    text = (
        ("K5 chọn cổ phiếu đại diện cho nhánh dùng mô hình. " if strategy == "HYBRID"
         else "K5 chọn cổ phiếu đại diện theo tương quan giá trong lịch sử đã ghim. ")
        if proof.get("applied_selection") == "equity-k5-v1"
        else "Tập tính toán giữ các tài sản đã được ghim cho phương pháp này. "
    )
    text += f"{len(active)} tài sản trong tập tính toán; {len(positive)} tài sản có tỷ trọng dương."
    if zero:
        text += " Tài sản trong tập tính toán nhận 0%: " + ", ".join(zero) + "."
    text += {
        "EW": " EW dùng tỷ trọng bằng nhau trên tập tính toán và đối chiếu các giới hạn đã ghim.",
        "MVO": " MVO dùng ước lượng lợi suất, covariance và các giới hạn đã ghim.",
        "BL_ML": " BL kết hợp prior, views, covariance và ràng buộc; chưa có attribution để gán một nguyên nhân riêng cho từng tỷ trọng.",
        "HYBRID": " Hệ thống phối hai nhánh phân bổ theo hồ sơ rủi ro và trạng thái thị trường.",
    }.get(strategy, " Chưa có attribution cho từng tỷ trọng.")
    add(
        "selection",
        "selection",
        text,
        ["facts.asset_ids", "facts.weights", "facts.selection_proof"]
        if proof
        else ["facts.asset_ids", "facts.weights"],
    )

    if q and q.views:
        for index, view in enumerate(q.views):
            if view.source_kind == "USER":
                add(
                    "user_view_" + str(index),
                    "views",
                    "View do người dùng cung cấp đã được ghim trong lần tính; nguồn này được phân biệt với dự báo ML và quy tắc phòng thủ.",
                    [f"quant.views.{index}"],
                )
                continue
            if view.source_kind == "POLICY":
                add(
                    "policy_view_" + str(index),
                    "views",
                    "View phòng thủ VFF là quy tắc tương đối so với phần còn lại của rổ, được đưa vào theo trạng thái rổ.",
                    [f"quant.views.{index}"],
                )
                continue
            asset = next(iter(view.coefficients))
            text = (
                f"{asset}: dự báo ensemble {percent(view.raw_mean_return)} trong 5 phiên, hướng "
                + (
                    "tăng"
                    if view.raw_mean_return > 0
                    else "giảm"
                    if view.raw_mean_return < 0
                    else "trung tính"
                )
                + "."
            )
            if view.status == "BELOW_THRESHOLD":
                text += " Dưới ngưỡng nên không được đưa thành view vào BL."
            else:
                text += f" Q áp dụng {percent(view.applied_q_daily)}/ngày sau biến đổi heuristic Option B; điểm confidence {view.confidence_applied:.3f}, không phải xác suất tăng giá."
            text += f" Tỷ trọng cuối cùng {percent(weights[asset])}; hướng dự báo không quyết định riêng tỷ trọng."
            add(
                "view_" + asset,
                "views",
                text,
                [f"quant.views.{index}", "facts.weights"],
            )
        for asset, features in q.features.items():
            labels = {
                "momentum_5": "Lợi suất 5 phiên đã qua",
                "momentum_10": "Lợi suất 10 phiên đã qua",
                "momentum_20": "Lợi suất 20 phiên đã qua",
                "rsi_14": "RSI14",
                "ma_ratio_10_30": "Tỷ lệ EMA10/30 trừ 1",
                "volatility_20": "Biến động lợi suất ngày 20 phiên",
                "macd_hist": "MACD histogram (nghìn VND)",
                "price_std_20": "Độ lệch chuẩn giá / giá trung bình 20 phiên",
            }
            values = "; ".join(
                labels[f.name]
                + ": "
                + (percent(f.value) if f.unit == "fraction" else f"{f.value:.3f}")
                for f in features
            )
            add(
                "features_" + asset,
                "features",
                f"Đầu vào quan sát của {asset}, kết thúc {q.history_end_date}: {values}. Các giá trị này mô tả đầu vào, chưa chứng minh mức đóng góp vào dự báo hoặc tỷ trọng.",
                [f"quant.features.{asset}", "quant.history_end_date"],
            )
    else:
        add(
            "views_missing",
            "views",
            f"{strategy} không sử dụng views ML trong kết quả này."
            if strategy in ("EW", "MVO")
            else "Lần tính này chưa lưu raw views và đặc trưng ML để đối chiếu. Không chạy lại model mới để giải thích kết quả cũ.",
            ["evidence.limitations"],
        )
    if not any(c.id == "views_missing" for c in claims):
        add(
            "views_missing",
            "views",
            "Chưa lưu view cho tài sản được hỏi trong đề xuất này; không thay bằng tín hiệu của mã khác.",
            ["evidence.limitations"],
        )
    add(
        "features_missing",
        "features",
        "Chưa lưu đặc trưng cho tài sản được hỏi trong đề xuất này; không thay bằng dữ liệu của mã khác.",
        ["evidence.limitations"],
    )
    add(
        "limitations",
        "limitations",
        "Dự báo có sai số; dữ liệu lịch sử chưa được chứng nhận đầy đủ theo thời điểm. Giải thích không thay đổi tỷ trọng và không tự chấp nhận mục tiêu.",
        ["evidence.limitations"],
    )
    return claims


def default_ids(claims, question=""):
    query = plain(question)
    group = (
        "features"
        if any(w in query for w in ("rsi", "dac trung", "macd", "momentum"))
        else "profile"
        if any(w in query for w in ("ho so", "than trong", "khau vi"))
        else "regime"
        if any(w in query for w in ("xu huong", "thi truong", "bien dong", "drawdown"))
        else "views"
        if any(w in query for w in ("view", "du bao", "tin hieu"))
        else "selection"
        if any(w in query for w in ("0%", "chon ma", "chon co phieu", "k5"))
        else None
    )
    if group:
        selected = [
            c.id for c in claims if c.group == group and not c.id.endswith("_missing")
        ]
        # Asset-focused questions take precedence within a selected topic.
        words = set(re.findall(r"\b[a-z0-9]+\b", query))
        named = {a for a in [*EQUITY_IDS, "GOLD", "VFF"] if a.lower() in words}
        matching = [
            c
            for c in claims
            if c.id in selected
            and any(a.isupper() and a.lower() in words for a in c.id.split("_")[1:])
        ]
        if group in ("views", "features") and named:
            selected = [c.id for c in matching] or [group + "_missing"]
        return (selected or [group + "_missing"])[:7] + ["limitations"]
    result = ["profile", "regime", "selection"]
    views = [c.id for c in claims if c.group == "views"]
    # Preserve both directions in an overview without pretending they determine weights.
    for direction in ("hướng tăng", "hướng giảm"):
        found = next(
            (c.id for c in claims if c.group == "views" and direction in c.text), None
        )
        if found:
            result.append(found)
    if not any(c in views for c in result):
        result += views[:1]
    return result + ["limitations"]


def render_claims(claims, selected_ids):
    by_id = {c.id: c for c in claims}
    if (
        not selected_ids
        or len(selected_ids) > 8
        or len(set(selected_ids)) != len(selected_ids)
        or not set(selected_ids) <= by_id.keys()
    ):
        raise ValueError("Unknown or repeated explanation claim")
    return "\n\n".join(by_id[i].text for i in selected_ids)


def validate_plan(plan, facts, evidence, claims, question=""):
    p = ClaimPlan.model_validate(plan)
    if (
        p.facts_hash != canonical_hash(facts)
        or p.evidence_hash != evidence["evidence_hash"]
    ):
        raise ValueError("Claim plan hash mismatch")
    render_claims(claims, p.selected_claim_ids)
    expected = default_ids(claims, question)
    expected_groups = {
        c.group for c in claims if c.id in expected and c.group != "limitations"
    }
    if len(expected_groups) == 1 and not set(expected) <= set(p.selected_claim_ids):
        raise ValueError("Missing requested asset/topic evidence")
    groups = {c.group for c in claims if c.id in p.selected_claim_ids}
    if not {c.group for c in claims if c.id in expected} <= groups:
        raise ValueError("Missing required explanation group")
    for direction in ("hướng tăng", "hướng giảm"):
        required = any(c.id in expected and direction in c.text for c in claims)
        if required and not any(
            c.id in p.selected_claim_ids and direction in c.text for c in claims
        ):
            raise ValueError("Omitted opposing view")
    return p.selected_claim_ids
