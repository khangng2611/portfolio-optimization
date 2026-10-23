"""Write evidence-backed findings; empirical baseline results remain unchanged."""
from pathlib import Path
import json,hashlib,shutil,re,csv
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/blocker_evidence_20261012';STEP=ROOT/'outputs/step1'
s=json.loads((OUT/'evidence_summary.json').read_text());g=s['gold'];v=s['vff'];st=s['stocks']
refit_path=OUT/'historical_fresh_refit/comparison_verification.json'
refit=json.loads(refit_path.read_text()) if refit_path.exists() else {}
complete=refit.get('both_phases_exact',False)
reproduction=('Đã huấn luyện mới IS/OOS bằng source/data commit `71cc107`, không cache; metrics, toàn bộ tỷ trọng và views khớp chính xác log gốc trong môi trường đã ghi nhận. Lượt tái lập kết thúc 27/02/2026. Manifest môi trường gốc chưa tìm thấy; năm lượt alpha chưa fit lại riêng.' if complete else 'Đã huấn luyện lại độc lập IS bằng source/data commit `71cc107`, không cache; metrics, tỷ trọng và views khớp chính xác nhật ký gốc. Lượt OOS với warm-up đầy đủ đang được kiểm tra; chưa được đánh dấu đạt trước khi có kết quả. Môi trường gốc chưa có manifest xác thực.')
section=f'''## 13. Các vấn đề cần giải quyết trước Step 2 (Blocking issues)

**Cập nhật chứng cứ ngày 12/10/2026:** đã truy nguồn chính thức, đối chiếu dữ liệu và thử tái lập độc lập. Các phép tính đã kiểm vẫn đạt, nhưng chứng cứ mới cho thấy chưa thể xem baseline tháng 4 là dữ liệu kinh tế đã được xác minh đầy đủ. **Mục 12.1 và các hình giữ nguyên lượt chạy 04/10 để đối chiếu; không phải kết quả chạy lại sau các phát hiện dưới đây.**

| Vấn đề | Chứng cứ đã xác minh | Phần còn phải giải quyết |
|---|---|---|
| Công bố VFF/GOLD | VFF tải lại khớp NAV gốc {v.get('refetched_nav_exact',0)}/{v.get('refetched_nav_overlap',0)} ngày. Có {v['metadata_present']}/552 timestamp FMarket; tất cả sau 15:00 ngày định giá, gồm {v['same_day_decisions_with_late_metadata']} ngày trùng quyết định. PNJ trả quote có giờ cập nhật. | `createdAt`/`updated_at` không chứng minh ngày công bố đầu tiên hoặc lịch sử sửa đổi. Cần vintage/cutoff theo lịch sử; không tự coi độ trễ một phiên là đủ. |
| Nguồn và cách lấy GOLD | Xác định nguồn dự kiến từ crawler là PNJ, SJC tại TPHCM, ngàn đồng/lượng. Trên {g['comparison_dates']} ngày có quote tải thành công, {g['baseline_matches_no_quote']} giá snapshot không khớp bất kỳ quote SJC/TPHCM cùng ngày. Ngày 29/04/2026: snapshot 167.500 khớp quote đầu; quote cuối trước 15:00 là 166.000. | Đã lưu raw và bảng đối chiếu; chuỗi ứng viên chưa kích hoạt và chưa đủ độ phủ. PNJ trả HTTP 429 cho {g['http_429_dates']} ngày; không coi tải thất bại là “không đổi giá”, không điền giá để che khoảng trống. Cần nguồn đủ kỳ và quy tắc chọn quote. |
| Điều chỉnh cổ phiếu | Đối chiếu KBS {st['symbols_checked']} mã, {st['common_observations']:,} ngày/mã chung: {st['fully_matching_symbols']} mã khớp toàn bộ, 8 mã thay đổi (DGC, FPT, GAS, HDB, MWG, TPB, VIB, VPB). Tài liệu Vnstock mô tả giá điều chỉnh; đã đối chiếu sự kiện ACB 2024/2025 bằng công bố FPTS/VSDC. | Chưa có ledger sự kiện đầy đủ 30 mã và công thức factor của KBS. Không gán mọi khác biệt cho cổ tức; không cộng cổ tức lần hai vào giá điều chỉnh. Cần chốt adjusted-close return hay total return có cash/share ledger. |
| Tái lập lượt lịch sử | {reproduction} | Không dùng việc khớp lượt tháng 2 để khẳng định có hồ sơ gốc đến tháng 4. Phạm vi tái lập và kỳ số liệu paper phải ghi rõ. |

**Lưu ý về giờ:** 15:00 là mốc chẩn đoán, không phải giờ quyết định đã được xác thực; nhật ký baseline chỉ ghi “after close”. Metadata sau 15:00 vì vậy chưa đủ kết luận một quyết định cụ thể bị leakage.

Bản cáo bạch VFF tháng 7/2023, 7/2025 và 3/2026 ghi **đóng sổ lệnh 14:40 ngày T−1**; bản 2023/2025 nêu giao dịch thứ Ba/thứ Năm. Vì vậy, mô phỏng close phiên kế tiếp trong mục 4/8 là quy ước định giá, chưa phải cơ chế khớp lệnh VFF thực tế. Các tài liệu này không tự xác nhận quy tắc cho toàn bộ 2020–2026. [Bản cáo bạch 2023](https://vinacapital.com/wp-content/uploads/2023/07/20230713_VFF-Ban-cao-bach-sua-doi-bo-sung-Jul-2023-002.pdf), [bản 2025](https://wm.vinacapital.com/wp-content/uploads/2025/07/20250725_VFF-Ban-cao-bach-sua-doi-bo-sung-07.2025-1.pdf), [bản 2026](https://wm.vinacapital.com/wp-content/uploads/2026/03/20260326_VFF-BCB-sua-doi-bo-sung-03.2026.pdf).

### Những lựa chọn cần thống nhất với giảng viên

| Mã | Đề xuất để quyết định | Ảnh hưởng và điều kiện |
|---|---|---|
| C1 — VFF và thời điểm thông tin | Ưu tiên mô phỏng theo công bố/lịch nhận lệnh thực tế khi có vintage đủ kỳ. Nếu chọn nghiên cứu trên chuỗi định giá, phải chấp nhận công khai giả định availability và độ trễ. | Độ trễ giả định là kịch bản, không phải chứng cứ loại bỏ leakage; có thể cần đổi lịch giao dịch và chạy lại. Cần thêm hồ sơ NAV/công bố 2020–2026 nếu đang lưu riêng. |
| C2 — GOLD | Đề xuất thay snapshot chưa đối chiếu được bằng quote SJC/TPHCM có nguồn, chọn quote cuối không muộn hơn cutoff đã chốt, giữ bid/ask và cờ carry. | Chỉ kích hoạt khi có nguồn đủ kỳ. Chọn giờ cutoff và cách định giá/giao dịch trước khi xem hiệu suất; snapshot cũ giữ làm đối chứng. |
| C3 — Lợi nhuận cổ phiếu | Chọn rõ nghiên cứu lợi nhuận trên giá đóng cửa điều chỉnh, hoặc tổng lợi nhuận có dòng tiền cổ tức và thay đổi số cổ phiếu. | Phương án tổng lợi nhuận cần ledger đầy đủ và tránh tính hai lần điều chỉnh. Không tự đổi mục tiêu nghiên cứu hoặc factor. |
| C4 — Điều kiện chuyển bước | Giảng viên chốt mức chứng cứ cần có khi chưa khôi phục đủ vintage lịch sử: tiếp tục bổ sung hay cho phép Step 2 trong phạm vi định giá với giả định được công khai. | Kỳ baseline tháng 4 đã được người nghiên cứu chốt, không cần xác nhận lại. Không chuyển thành READY nghiêm ngặt chỉ bằng chú thích; ghi riêng lượt lịch sử đến 27/02 và baseline đến 29/04. |

**Minh chứng nộp bổ sung:** `15_Blocker_Evidence_20261012.zip` chứa raw public sources, manifest/hashes, đối chiếu VFF/GOLD/30 cổ phiếu và hồ sơ thử tái lập. `16_Decisions_To_Confirm.md` tổng hợp bốn lựa chọn C1–C4 và hồ sơ cần cung cấp. Đây là hai tệp mới đặt cùng thư mục với bộ minh chứng trước. Không gửi liên hệ cho nhà cung cấp/giảng viên trong lần kiểm tra này.

Nguồn bổ sung: [PNJ](https://giavang.pnj.com.vn/), [Vnstock về nguồn dữ liệu](https://vnstocks.com/docs/vnstock/tham-khao/data-sources), [công bố ACB của VSDC](https://vsdc.vn/en/ad/182839). Manifest ghi cả lỗi HTTP và độ phủ kiểm chứng; nguồn hiện tại không thay thế được lịch sử phiên bản dữ liệu.

**Kết luận:** đã bổ sung chứng cứ và tái lập lượt lịch sử, nhưng availability, GOLD đủ kỳ và định nghĩa lợi nhuận vẫn cần chốt. 33 input baseline giữ nguyên. Cần xử lý hoặc thống nhất phạm vi trước Step 2; universe, chi phí và ablation thuộc các bước sau.

NOT READY FOR STEP 2
'''
(OUT/'report_section13.md').write_text(section)
decisions=section[section.index('### Những lựa chọn'):section.index('**Minh chứng nộp bổ sung:**')]
(OUT/'16_Decisions_To_Confirm.md').write_text('# Những lựa chọn cần xác nhận trước Step 2\n\nNgày 12/10/2026. Chưa có lựa chọn nào dưới đây được mặc định là đã phê duyệt.\n\n'+decisions+'\nHồ sơ hữu ích cần cung cấp nếu có: raw GOLD kèm giờ/khu vực/cờ điền; NAV VFF và thời điểm công bố; quy tắc điều chỉnh và ledger cổ tức 30 mã; manifest môi trường/model/log paper đến tháng 4. Không cần gửi thông tin đăng nhập hoặc khóa API.\n')
detail=f'''# Chứng cứ cho bốn vấn đề trước Step 2

Ngày kiểm tra 12/10/2026. Phân biệt chứng cứ trực tiếp, suy luận và giới hạn; không đổi input/mô hình của baseline tháng 4.

## VFF và chronology

- Tải lại API FMarket productId=21, kết thúc yêu cầu 30/04/2026: {v.get('refetched_nav_exact',0)}/{v.get('refetched_nav_overlap',0)} NAV khớp chính xác bản 04/10, không chỉ giá làm tròn. Hai lần tải giống nhau không xác nhận dữ liệu chưa từng được sửa trước đó.
- Trong 552 ngày NAV, 508 có record-created timestamp, 44 thiếu. 508 timestamp sau 15:00 ngày định giá; 16 sang ngày sau hoặc muộn hơn. Có 123 ngày NAV trùng quyết định; 115 có metadata sau 15:00. Đây là cảnh báo về giả định availability, không phải chứng cứ rằng website chính thức chắc chắn công bố muộn.
- Trang chính thức hiện tại liệt kê NAV 07/10/2026 đăng 08/10 và NAV 30/09 đăng 01/10. Các ví dụ ngoài mẫu chỉ chứng minh ngày định giá khác ngày đăng có thể xảy ra, không áp toàn kỳ. Trang bị HTTP403 khi tải raw trực tiếp nhưng đã đọc qua web tool; không coi HTML403 là tài liệu công bố.
- Bản cáo bạch 2023 trang31/35–36, 2025 trang32, 2026 trang31/35 xác nhận quy tắc đóng sổ và định giá/công bố. Không ngoại suy phiên bản 2026 về năm2020. Không nhầm thời gian xác nhận giao dịch T+3 với thời điểm công bố NAV.

## GOLD

- Source truy được từ mã crawler: PNJ edge API, TPHCM, SJC sell. Đơn vị ngàn đồng/lượng được xác nhận bằng trang PNJ; đổi sang VND phải nhân1000 nếu cần định lượng, không nhân1000 vào return. Không gọi quote first là giá close.
- Thu hồi thử {g['calendar_dates_attempted']} ngày trong mẫu: {g['http_success_dates']} ngày HTTP200, {g['http_429_dates']} ngày HTTP429. {g['dates_with_quotes']} ngày có quote SJC, {g['successful_dates_without_quotes']} ngày phản hồi hợp lệ nhưng không có quote. Không có bằng chứng về giá tại các ngày tải lỗi. Collector đã được sửa để dừng khi gặp429; không thực hiện lượt thu hồi tiếp.
- Trong {g['comparison_dates']} ngày có quote: snapshot khớp bất kỳ quote ở {g['baseline_matches_any_quote']} ngày, không khớp ở {g['baseline_matches_no_quote']} ngày. Kết quả là đối chiếu mẫu, không ước lượng tỷ lệ lỗi toàn kỳ.
- 29/04/2026:167500 ngàn đồng/lượng tại07:57:40/07:59:59;166000 tại08:45:04/08:45:11. Snapshot167500 khớp đầu ngày. 01/01/2020 API không có quote nhưng snapshot42600; chưa thể gọi đây là giá thực hoặc giá carry nếu không có seed provenance.
- `gold_raw_quotes.csv` giữ quote timestamp, giá mua/bán, location, raw member. `gold_snapshot_daily_comparison.csv` phân biệt retrieval failure với successful-no-quotes. `gold_candidate_1500_NOT_ACTIVATED.csv` là mẫu chưa đủ độ phủ, chưa carry qua ngày tải lỗi, chưa làm input backtest. Timestamp không có timezone; giả định VN được khai báo, chưa xác nhận first-publication/revision vintage.

## Cổ phiếu

- Crawler đặt nguồnKBS. Truy lại30mã giai đoạn2020–04/2026 đượcHTTP200 với headers chuẩn; các lỗi400 ban đầu giữ trong manifest, không tính là dữ liệu hợp lệ. Có {st['common_observations']:,} hàng ngày/mã chung;22mã khớp hoàn toàn,8mã đã thay đổi. Không thay snapshot hiện tại.
- `stock_snapshot_comparison.csv` có sai lệch mức giá, return và khoảng tỷ lệ; `stock_overlap_SYMBOL.csv` là đối chiếu từng ngày. Thay đổi mức giá không tự chứng minh thay đổi return hoặc lý do corporate action.
- Tài liệu chính thức của Vnstock mô tả KBS/VCI trả giá điều chỉnh khác nhau. Đây là tài liệu hiện tại của thư viện, không phải chứng nhận công thức factor của snapshot2020–2026.
- Sự kiện ACB đối chiếu: FPTS31/05/2024 trang8 ghi ex-date31/05/2024, cash1000đ/cp và stock100:15; VSDC15/05/2025 ghi record26/05/2025, cash1000đ trả05/06/2025 và stock100:15. Đây là4hàng mẫu, không phải ledger30mã hoàn chỉnh.
- KBS event endpoint s=500 báo lỗi(max20); truy lạiACB s=20 trả[] nên không dùng làm bằng chứng “không có sự kiện”. Cần ledger/factor đầy đủ trước khi chứng nhận total return.

## Tái lập và phạm vi

{reproduction}

Manifest trong `historical_fresh_refit/` ghi source hash, isolated workspace, lệnh, môi trường, seeds42–46, no-cache và exit status. Mã/data snapshot gốc không sửa. Tái lập mô hình không sửa các lỗi chronology/holdings của logic gốc; đó là đối chứng lịch sử.

## Điều kiện và quyết định

{decisions}

## Nguồn chính thức

- VinaCapital VFF page: https://wm.vinacapital.com/vi/investment-solutions/onshore-funds/vff/
- VFF2023: https://vinacapital.com/wp-content/uploads/2023/07/20230713_VFF-Ban-cao-bach-sua-doi-bo-sung-Jul-2023-002.pdf
- VFF2025: https://wm.vinacapital.com/wp-content/uploads/2025/07/20250725_VFF-Ban-cao-bach-sua-doi-bo-sung-07.2025-1.pdf
- VFF2026: https://wm.vinacapital.com/wp-content/uploads/2026/03/20260326_VFF-BCB-sua-doi-bo-sung-03.2026.pdf
- PNJ: https://giavang.pnj.com.vn/
- Vnstock sources: https://vnstocks.com/docs/vnstock/tham-khao/data-sources
- Vnstock migration: https://vnstocks.com/docs/vnstock/v5/chuyen-doi/tu-vnstock-data-3x
- VSDC ACB2025: https://vsdc.vn/en/ad/182839
- FPTS2024: https://file.fpts.com.vn/FileStore2/File/2024/05/31/FIA20240531_8c0c8a23.pdf

NOT READY FOR STEP 2
'''
(OUT/'blocker_evidence_summary.md').write_text(detail)
print(json.dumps(dict(main_section_words=len(section.split()),refit_both_exact=complete)))
