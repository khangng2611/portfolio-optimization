"""Finite Vietnamese claims grounded in frozen run evidence and canonical facts."""

from decimal import Decimal, ROUND_HALF_UP
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
    summary: str | None = Field(default=None, max_length=1000)
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

    def add(identity, group, text, refs, summary=None):
        claims.append(
            ExplanationClaim(
                id=identity,
                group=group,
                template_id=group + "-v1",
                text=text,
                summary=summary,
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
        summary = "Hồ sơ đã ghim: " + labels[profile["profile"]] + "."
        if answers.get("horizon_months") is not None:
            summary += f" Thời hạn {int(answers['horizon_months'])} tháng."
        if constraints.get("max_non_defensive_weight") is not None:
            summary += f" Phòng thủ tối thiểu hiệu lực {percent(lower)}."
        if constraints.get("max_position_weight") is not None:
            summary += (
                f" Mỗi tài sản tối đa {percent(constraints['max_position_weight'])}."
            )
        add(
            "profile",
            "profile",
            text,
            ["facts.risk_profile", "facts.constraints"],
            summary,
        )
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
            f"Rổ đã ghim ở trạng thái {state}: tỷ lệ biến động 20/120 phiên {regime['vol_ratio']:.2f}; drawdown cuối cửa sổ 60 phiên {percent(regime['drawdown'])}; lợi suất ngày trung bình 60 phiên {percent(regime['equity_momentum'])}.",
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
        (
            "K5 chọn cổ phiếu đại diện cho nhánh dùng mô hình. "
            if strategy == "HYBRID"
            else "K5 chọn cổ phiếu đại diện theo tương quan giá trong lịch sử đã ghim. "
        )
        if proof.get("applied_selection") == "equity-k5-v1"
        else "Tập tính toán giữ các tài sản đã được ghim cho phương pháp này. "
    )
    text += f"{len(active)} tài sản trong tập tính toán; {len(positive)} tài sản có tỷ trọng dương."
    if zero:
        text += " Tài sản trong tập tính toán nhận 0%: " + ", ".join(zero) + "."
    selection_summary = text
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
        selection_summary,
    )

    ranked = sorted(
        ((asset, weight) for asset, weight in weights.items() if float(weight) > 0),
        key=lambda item: -Decimal(str(item[1])),
    )
    overview = f"Đề xuất phân bổ vốn vào {len(ranked)} tài sản."
    if ranked:
        overview += " Tỷ trọng cao nhất gồm " + ", ".join(
            f"{asset} {percent(weight)}" for asset, weight in ranked[:3]
        ) + "."
    profile_label = labels.get(profile.get("profile"))
    horizon = (profile.get("answers") or {}).get("horizon_months")
    if profile_label:
        overview += "\n\nHồ sơ " + profile_label + (f", thời hạn {horizon} tháng." if horizon is not None else ".")
    defensive = constraints.get("defensive_asset_ids")
    floors = []
    if constraints.get("min_defensive_weight") is not None:
        floors.append(Decimal(str(constraints["min_defensive_weight"])))
    if constraints.get("max_non_defensive_weight") is not None:
        floors.append(1 - Decimal(str(constraints["max_non_defensive_weight"])))
    if isinstance(defensive, list) and set(defensive) <= weights.keys():
        actual = sum(Decimal(str(weights[asset])) for asset in set(defensive))
        overview += f" Nhóm phòng thủ chiếm {percent(actual)}"
        overview += f", so với mức tối thiểu {percent(max(floors))}." if floors else "."
    elif floors:
        overview += f" Mức phòng thủ tối thiểu là {percent(max(floors))}. Chưa đủ dữ kiện để đối chiếu tỷ trọng thực tế."
    refs = ["facts.asset_ids", "facts.weights", "facts.constraints", "facts.risk_profile"]
    if proof:
        refs.append("facts.selection_proof")
    if regime:
        overview += f"\n\nTại thời điểm tính, rổ tài sản ở trạng thái {state}."
        refs.append("quant.regime" if q and q.regime else "facts.selection_context.regime")
    if e.status != "COMPLETE":
        overview += " Đề xuất chưa lưu đầy đủ dữ kiện giải thích."
    overview += " Hệ thống không tự chấp nhận mục tiêu."
    refs.append("evidence.status")
    add("allocation_overview", "selection", overview + "\n\n" + text, refs, overview)

    for index, (asset, weight) in enumerate(weights.items()):
        add(
            "weight_" + asset, "selection",
            f"Trong đề xuất đã lưu, {asset} có tỷ trọng {percent(weight)}. "
            "Dữ kiện đã lưu chưa đủ để kết luận nguyên nhân riêng cho tỷ trọng này.",
            [f"facts.asset_ids.{index}", f"facts.weights.{index}"],
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
            summary = text + f" Tỷ trọng {percent(weights[asset])}."
            if view.status == "BELOW_THRESHOLD":
                text += " Dưới ngưỡng nên không được đưa thành view vào BL."
                summary += " Dưới ngưỡng, không áp dụng vào BL."
            else:
                text += f" Q áp dụng {percent(view.applied_q_daily)}/ngày sau biến đổi heuristic Option B; điểm confidence {view.confidence_applied:.3f}, không phải xác suất tăng giá."
            text += f" Tỷ trọng cuối cùng {percent(weights[asset])}; hướng dự báo không quyết định riêng tỷ trọng."
            add(
                "view_" + asset,
                "views",
                text,
                [f"quant.views.{index}", "facts.weights"],
                summary,
            )
            add(
                "view_details_" + asset,
                "views",
                text,
                [f"quant.views.{index}", "facts.weights"],
            )
        ml_views = [v for v in q.views if v.source_kind == "ML"]
        if ml_views:
            positive_count = sum(v.raw_mean_return > 0 for v in ml_views)
            negative_count = sum(v.raw_mean_return < 0 for v in ml_views)
            coverage = (
                f"Trong {len(ml_views)} ML views đã lưu: {positive_count} dương, {negative_count} âm."
                + (
                    " Không có view âm trong các views này."
                    if not negative_count
                    else ""
                )
                if e.status == q.status == "COMPLETE"
                else "Dữ kiện đã lưu chưa đủ để kết luận về dấu của toàn bộ views."
            )
            add("view_coverage", "views", coverage, ["quant.views", "evidence.status"])
    else:
        add(
            "views_missing",
            "views",
            f"{strategy} không sử dụng views ML trong kết quả này."
            if strategy in ("EW", "MVO")
            else "Lần tính này chưa lưu views ML để đối chiếu. Không chạy lại model mới để giải thích kết quả cũ.",
            ["evidence.limitations"],
        )
    if not any(c.id == "views_missing" for c in claims):
        add(
            "views_missing",
            "views",
            "Chưa lưu view cho tài sản được hỏi trong đề xuất này; không thay bằng tín hiệu của mã khác.",
            ["evidence.limitations"],
        )
    if q:
        for asset, features in q.features.items():
            if not features:
                continue
            date_label = (
                f"đến {q.history_end_date}"
                if q.history_end_date
                else "chưa lưu ngày dữ liệu"
            )
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
                f"Đầu vào quan sát của {asset}, {date_label}: {values}. Các giá trị này mô tả đầu vào, chưa chứng minh mức đóng góp vào dự báo hoặc tỷ trọng.",
                [f"quant.features.{asset}", "quant.history_end_date"],
                f"Đã lưu {len(features)} đặc trưng đầu vào của {asset} ({date_label}); có thể mở chi tiết để đối chiếu từng chỉ số.",
            )
            for index, feature in enumerate(features):
                value = (
                    percent(feature.value)
                    if feature.unit == "fraction"
                    else f"{feature.value:.3f}".replace(".", ",")
                )
                add(
                    f"features_{asset}_{feature.name}",
                    "features",
                    f"{asset} · {labels[feature.name]}: {value} ({date_label}).",
                    [f"quant.features.{asset}.{index}", "quant.history_end_date"],
                )
    add(
        "features_missing",
        "features",
        "Chưa lưu chỉ số hoặc đặc trưng được hỏi trong đề xuất này.",
        ["evidence.limitations"],
    )
    for group in ("features", "views"):
        add(
            f"{group}_scope_required",
            group,
            "Hãy chọn ít mã hoặc chỉ số hơn, hoặc mở phần dữ kiện chi tiết để xem toàn bộ.",
            ["evidence.status"],
        )
    caution = "Dự báo có sai số; tín hiệu không quyết định riêng tỷ trọng."
    if "PIT_NOT_CERTIFIED" in e.limitations or (q and "PIT_NOT_CERTIFIED" in q.limitations):
        caution += " Dữ liệu lịch sử chưa được chứng nhận đầy đủ theo thời điểm."
    add(
        "limitations", "limitations", caution + " Hệ thống không tự chấp nhận mục tiêu.",
        ["quant.limitations" if q else "evidence.limitations"],
    )
    return claims


def method_requested(question):
    query = plain(question)
    return bool(re.search(
        r"black[\s–-]*litterman|machine learning|\bbl\s*[+_]\s*ml\b|"
        r"cach tinh|phuong phap (?:tinh|phan bo)|"
        r"(?:tinh|phan bo).{0,60}(?:the nao|nhu the nao|bang cach nao)", query,
    ))


def allocation_method(facts):
    strategy = facts.get("strategy")
    if strategy == "HYBRID":
        return (
            "Hệ thống phối hai cách tính theo hồ sơ rủi ro và trạng thái thị trường tại lần tính. "
            "Một phần dựa trên lợi nhuận và biến động lịch sử. Phần còn lại dùng Black–Litterman "
            "kết hợp học máy (Machine Learning). Mô hình dự báo tạo tín hiệu, rồi Black–Litterman "
            "kết hợp tín hiệu theo độ tin cậy với ước lượng lợi nhuận ban đầu. "
            "Các giới hạn của danh mục là đầu vào của lần tính."
        )
    if strategy == "BL_ML":
        return (
            "Đề xuất này dùng Black–Litterman để kết hợp ước lượng lợi nhuận ban đầu với các tín hiệu "
            "dự báo và độ tin cậy của chúng. Học máy (Machine Learning) cung cấp tín hiệu khi lần tính "
            "có mô hình phù hợp. Hệ thống dùng kết quả đó cùng hồ sơ rủi ro và các giới hạn để tính tỷ trọng."
        )
    return {
        "EW": "Đề xuất đã lưu này chia đều tỷ trọng giữa các tài sản được dùng trong lần tính.",
        "MVO": "Đề xuất đã lưu này tính tỷ trọng từ lợi nhuận và biến động lịch sử cùng giới hạn rủi ro của danh mục.",
    }.get(strategy, "Lần tính này chưa có thông tin về cách tạo đề xuất.")


def detail_requested(question):
    return bool(
        re.search(
            r"chi tiet|day du|tat ca (?:cac )?dac trung|toan bo (?:cac )?dac trung|giai thich ky",
            plain(question),
        )
    )


def focused_weight(facts, focus):
    asset = focus["asset"]
    idx = facts["asset_ids"].index(asset)
    text = f"{asset} chiếm {percent(facts['weights'][idx])} trong đề xuất đã lưu."
    refs = [f"facts.asset_ids.{idx}", f"facts.weights.{idx}"]
    if focus["field"] == "amount":
        value = Decimal(str(facts["weights"][idx])) * Decimal(str(facts["capital_vnd"]))
        dong = format(value.quantize(Decimal(1), rounding=ROUND_HALF_UP), ",").replace(",", ".")
        text += f" Số tiền mục tiêu theo vốn tại thời điểm tính là {dong} ₫."
        refs.append("facts.capital_vnd")
    if focus["field"] == "reason":
        limits = facts.get("constraints") or {}
        if asset in (limits.get("defensive_asset_ids") or []):
            floors = [float(limits["min_defensive_weight"])] if limits.get("min_defensive_weight") is not None else []
            if limits.get("max_non_defensive_weight") is not None:
                floors.append(1 - float(limits["max_non_defensive_weight"]))
            if floors:
                text += f" {asset} thuộc nhóm phòng thủ. Giới hạn đã ghim yêu cầu cả nhóm đạt ít nhất {percent(max(floors))}."
                refs.append("facts.constraints")
        hybrid = (facts.get("diagnostics") or {}).get("hybrid") or {}
        share = hybrid.get("mvo_share")
        mvo, bl = hybrid.get("mvo_weights"), hybrid.get("bl_ml_weights")
        size = len(facts["asset_ids"])
        if (facts.get("strategy") == "HYBRID" and isinstance(mvo, list) and isinstance(bl, list)
            and len(mvo) == len(bl) == size
            and all(type(v) in (float, int) and 0 <= v <= 1 + 1e-12 for v in (share, mvo[idx], bl[idx]))
            and abs(share * mvo[idx] + (1 - share) * bl[idx] - float(facts["weights"][idx])) <= 1e-12):
            text += (f" Nhánh MVO dành {percent(mvo[idx])} cho {asset}, nhánh BL_ML dành {percent(bl[idx])}."
                     f" Đề xuất phối hai nhánh theo tỷ lệ {percent(share)} và {percent(1 - share)}.")
            refs.extend(["facts.diagnostics.hybrid.mvo_share", f"facts.diagnostics.hybrid.mvo_weights.{idx}",
                         f"facts.diagnostics.hybrid.bl_ml_weights.{idx}"])
        else:
            text += " Dữ kiện đã lưu chưa đủ để xác định nguyên nhân riêng cho đúng tỷ trọng này."
    return ExplanationClaim(id="focus_" + asset, group="selection", template_id="saved-weight-v1", text=text, refs=refs)


def default_ids(claims, question=""):
    query = plain(question)
    group = (
        "features"
        if any(w in query for w in ("rsi", "dac trung", "macd", "momentum"))
        else "profile"
        if any(w in query for w in ("ho so", "than trong", "khau vi"))
        else "regime"
        if any(
            w in query
            for w in ("xu huong", "thi truong", "bien dong", "drawdown", "rui ro")
        )
        else "views"
        if any(w in query for w in ("view", "du bao", "tin hieu", "confidence"))
        or re.search(r"\bq\b", query)
        else "selection"
        if any(w in query for w in ("0%", "chon ma", "chon co phieu", "k5"))
        else None
    )
    if group in (None, "selection", "profile") and re.search(
        r"\b(?:ty trong|phan bo|chon|dua|tai sao|vi sao|ly do)\b", query,
    ):
        named_weights = [c.id for c in claims if c.id.startswith("weight_")
                         and re.search(r"\b" + re.escape(c.id[7:].lower()) + r"\b", query)]
        if named_weights and len(named_weights) <= 7:
            return named_weights + (["profile"] if group == "profile" else [])
    if group == "selection":
        return ["selection"]
    if group:
        selected = [
            c.id
            for c in claims
            if c.group == group and not c.id.endswith(("_missing", "_scope_required"))
        ]
        words = set(re.findall(r"\b[a-z0-9]+\b", query))
        named = {a for a in [*EQUITY_IDS, "GOLD", "VFF"] if a.lower() in words}
        # Preserve an explicit ticker even if it is outside this run's catalog.
        named.update(
            set(re.findall(r"\b[A-Z]{3,5}\b", question))
            - {"RSI", "MACD", "EMA", "MVO", "ML", "PIT", "NAV", "VNINDEX", "OPTION"}
        )
        if group == "features":
            periods = set(re.findall(r"\brsi\s*(\d+)\b", query))
            metrics = []
            if "rsi" in query:
                metrics.append(
                    "rsi_14" if not periods or periods == {"14"} else "unsupported"
                )
            if "macd" in words:
                metrics.append("macd_hist")
            if "momentum" in words:
                requested = words.intersection(re.findall(r"\b\d+\b", query))
                horizons = requested or {"5", "10", "20"}
                metrics.extend("momentum_" + period for period in sorted(horizons))
            if metrics:
                selected = [
                    i for i in selected if any(i.endswith("_" + m) for m in metrics)
                ]
            else:
                selected = [i for i in selected if len(i.split("_")) == 2]
        elif group == "views":
            technical = "confidence" in words or "q" in words
            selected = [
                i for i in selected if i.startswith("view_details_") == technical
            ]
            if (
                not named
                and re.search(r"co .*view.*am|view.*am.*nao", query)
                and "view_coverage" in selected
            ):
                selected = ["view_coverage"]
        if group in ("views", "features") and named:
            selected = [i for i in selected if named.intersection(i.split("_")[1:])]
            if any(not any(a in i.split("_")[1:] for i in selected) for a in named):
                selected.append(group + "_missing")
        if (
            group == "features"
            and metrics
            and any(not any(i.endswith("_" + m) for i in selected) for m in metrics)
        ):
            if "features_missing" not in selected:
                selected.append("features_missing")
        if len(selected) > (7 if group == "views" else 8):
            return [f"{group}_scope_required"]
        return (selected or [group + "_missing"]) + (
            ["limitations"] if group == "views" else []
        )
    if not detail_requested(question):
        return ["allocation_overview"]
    result = ["profile", "regime", "selection"]
    views = [c.id for c in claims if c.group == "views"]
    # Preserve both directions in an overview without pretending they determine weights.
    for direction in ("hướng tăng", "hướng giảm"):
        found = next(
            (
                c.id
                for c in claims
                if c.group == "views"
                and not c.id.startswith("view_details_")
                and direction in c.text
            ),
            None,
        )
        if found:
            result.append(found)
    if not any(c in views for c in result):
        result += views[:1]
    if any(c.id == "view_coverage" for c in claims):
        result.append("view_coverage")
    return result + ["limitations"]


def render_claims(claims, selected_ids, *, concise=False):
    by_id = {c.id: c for c in claims}
    if (
        not selected_ids
        or len(selected_ids) > 8
        or len(set(selected_ids)) != len(selected_ids)
        or not set(selected_ids) <= by_id.keys()
    ):
        raise ValueError("Unknown or repeated explanation claim")
    return "\n\n".join(
        (by_id[i].summary or by_id[i].text) if concise else by_id[i].text
        for i in selected_ids
    )


def validate_plan(plan, facts, evidence, claims, question=""):
    p = ClaimPlan.model_validate(plan)
    if (
        p.facts_hash != canonical_hash(facts)
        or p.evidence_hash != evidence["evidence_hash"]
    ):
        raise ValueError("Claim plan hash mismatch")
    render_claims(claims, p.selected_claim_ids)
    expected = default_ids(claims, question)
    if set(p.selected_claim_ids) != set(expected):
        raise ValueError("Missing or unrelated requested evidence")
    return p.selected_claim_ids
