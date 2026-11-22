# Vnstock 4 → thế hệ 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Không triển khai chỉ vì tài liệu này đã được tạo; yêu cầu hiện tại là lập kế hoạch.

**Goal:** Chuyển toàn bộ luồng Vnstock 4 đang hoạt động sang `vnstock==6.0.1` và `vnstock-oapi==0.1.2`, dùng FHSC, giữ nguyên từng byte dữ liệu và bằng chứng nghiên cứu hiện tại.

**Architecture:** Sửa trên bản sao mã nguồn, chạy ingestion trong môi trường Python riêng, ghi mọi dữ liệu mới vào `vnstock-migration/gen6/<run-id>/`. Giữ hợp đồng CSV đầu ra cho các bộ đọc hiện có; mọi khác biệt KBS/FMarket → FHSC được ghi nhận, không dùng để sửa lại baseline. Các bản mã lịch sử được bảo tồn và loại khỏi phạm vi thực thi đang hoạt động.

**Tech Stack:** Python 3.12, Vnstock 6.0.1, vnstock-oapi 0.1.2, pandas, pytest, Docker Compose hiện có. Không thêm thư viện biểu đồ hoặc framework ingestion.

**Spec:** Yêu cầu ngày 21/11/2026 của người dùng: “migrate toàn bộ phần dùng vnstock 4 lên thế hệ 6, giữ nguyên dữ liệu nghiên cứu hiện tại và chỉ rõ những bước cần tôi cung cấp key FHSC”. Các quyết định kỹ thuật bên dưới là đề xuất để thực hiện yêu cầu này.

## Global Constraints

- Không sửa/xóa/ghi đè dữ liệu nghiên cứu, universe, model, snapshot hoặc kết quả đã lưu; không tự tải bù vào lịch sử cũ.
- Không chạy crawler đời 4 để lấy baseline: bản cũ đã ngừng xác thực từ 10/11/2026. Chỉ đọc package metadata và kết quả đã lưu.
- Không cài đè `venv`, `.venv-software`, Python hệ thống; không đổi seed, cấu hình nghiên cứu, thuật toán backtest hoặc model.
- Ghim `vnstock==6.0.1`, `vnstock-oapi==0.1.2`; dùng `--extra-index-url https://vnstocks.com/api/packages`. Giữ các pin số học hiện tại; nếu resolver xung đột, báo rõ thay vì tự nâng numpy/pandas/scikit-learn.
- Dùng nguồn `fhsc` được đề xuất theo yêu cầu key của người dùng; không fallback ngầm sang KBS, SSI hoặc nguồn khác.
- Giữ `compat="v5"` khi gọi API thế hệ 6. Đây là hồ sơ tương thích cột thế hệ 5, không phải cam kết dữ liệu giống Vnstock 4.
- Không đọc/in key, `.env` hay kho thông tin xác thực; người dùng tự nhập key trên Terminal hoặc secret store. Báo cáo chỉ ghi trạng thái kiểm tra.
- Không tự train lại, chạy toàn bộ nghiên cứu, approve model, publish bundle, accept proposal, sửa catalog hoặc cập nhật database ứng dụng trong kiểm thử migration.
- Giữ nguyên các thay đổi đang làm dở trong working tree; chỉ áp dụng các hunk của migration, không `git reset`, `stash` hoặc tạo commit chứa công việc khác.

## Review Focus

1. Đường dẫn output trỏ vào dataset cũ, thư mục cha hoặc symlink: phải từ chối trước khi gọi mạng/ghi tệp — Task 2.
2. Nến có timezone, trùng ngày, null volume, trả thiếu lịch sử hoặc nến chưa đóng: không lệch ngày hoặc âm thầm lấy 100 dòng gần nhất — Task 3.
3. Giá nghìn đồng bị chia thêm 1.000, basis FHSC chưa xác nhận: không tạo pack sai đơn vị/basis — Task 3.
4. Quỹ trả đúng bảng nhưng sai danh tính, NAV khác nhau giữa các nguồn: không gán lại ticker để hợp thức hóa dữ liệu — Task 4.
5. Key thiếu/sai hoặc nguồn từ chối, lỗi chứa secret, container dùng image cũ: không mất dữ liệu tốt và không báo kiểm thử thành công — Task 5–6.

## Hiện trạng và phạm vi

Rà soát ngày 21/11/2026: không tìm thấy notebook ngoài các môi trường/dependency. Có ba entry point hoạt động dùng API đời 4. Các tham chiếu phiên bản trong báo cáo là provenance lịch sử, không phải lời gọi cần chuyển.

| Nơi | Hiện trạng | Xử lý |
| --- | --- | --- |
| `crawl/stock.py` | Import `vnstock.ui`; KBS; danh sách VN30; OHLCV cổ phiếu, ETF E1VFVN30 và VNINDEX; ghi thẳng `datasets/` | Chuyển API/nguồn, thêm output an toàn, bảo toàn schema CSV |
| `crawl/fund.py` | `Reference().fund.list()`; đọc `short_name`; `Market().fund(symbol).nav()`; chia NAV/1.000 | Chuyển FHSC; đọc `ticker`, `time/nav`; xác minh danh tính và đơn vị |
| `scripts/fetch_serving_prices.py` | Từ chối ngoài 4.x; `vnstock.ui.Market`; KBS; tạo pack/manifest | Chuyển 6.x/FHSC, giữ hợp đồng với bên nhập pack |
| `requirements.txt` | `vnai==2.5.0`, `vnstock==4.0.4`, `vnstock_ezchart==1.0.2` | Bỏ ba pin cũ khỏi dependency đang hoạt động; không đụng bản requirements lịch sử |
| `scripts/smoke_market_quant.py` | Đọc `time/close`, manifest `thousand_VND/share`, `provider_adjusted`; có nhiều bước ghi DB, train/approve/publish | Giữ hợp đồng pack; kiểm tra bằng fixture. Không chạy end-to-end trên stack đang dùng |
| `scripts/setup_software.py` | Đưa fetch script vào lint gate | Giữ gate và cập nhật danh sách test/lint khi cần |
| `services/market-data/{pyproject.toml,requirements.lock,Dockerfile}` | Đã ghim/cài 6.0.1 và oapi 0.1.2 trong thay đổi hiện tại | Tái kiểm tra, không làm lại hoặc ghi đè thay đổi có sẵn |
| `asset_metadata.py`, Compose profile `metadata` | Đã dùng `Reference('fhsc').company(asset).info()` và nhận `FHSC_API_KEY` | Kiểm thử thật chỉ đọc; không chạy sync ghi DB ở giai đoạn đối chiếu |
| `refresh_provider.py`, `phase1_full.py`, `selected_refresh.py`, `refresh_worker.py`, `scripts/fit_phase1_local.py` | Dùng HTTP KBS trực tiếp hoặc gọi adapter của nó, không import/chạy Vnstock 4 | Không đổi provider trong migration thư viện này; kiểm tra không vô tình phụ thuộc đời 4. Chuyển các luồng HTTP này sang FHSC là thay đổi nguồn riêng |
| `trusted_baseline/`, `legacy_version/`, mã trong `outputs/...` | Snapshot lịch sử còn chứa pin/import đời 4 | Giữ nguyên, đánh dấu là lưu trữ; không đưa vào lệnh chạy mới |
| `report.md`, scripts tạo báo cáo Step1 | Ghi lại phiên bản và lỗi của lần nghiên cứu cũ | Giữ sự thật lịch sử, không thay số phiên bản trong báo cáo bằng 6.0.1 |

### Tệp dự kiến thay đổi/tạo khi thực hiện

- Sửa: `crawl/stock.py`, `crawl/fund.py`, `scripts/fetch_serving_prices.py`, `requirements.txt`, `.gitignore`, `QUICKSTART.md`, `docs/PROJECT_CONTEXT.md`, `docs/software/MARKET_QUANT_BRIDGE.md`.
- Tạo: `requirements-vnstock6.txt` (index và hai pin Vnstock); `crawl/vnstock_io.py` (nguồn ingestion tập trung, chuẩn hóa ngày, bảo vệ output dùng chung cho ba entry point).
- Tạo test: `tests/software/test_vnstock_crawl_io.py`, `tests/software/test_vnstock_stock.py`, `tests/software/test_vnstock_fund.py`, `tests/software/test_fetch_serving_prices.py`.
- Kiểm tra/cập nhật tối thiểu nếu contract test phát hiện cần thiết: `scripts/smoke_market_quant.py`, `scripts/setup_software.py`, `tests/software/test_asset_metadata_sync.py`, ba tệp build/dependency market-data nói trên và `infra/local/compose.yaml`.
- Không tạo hướng dẫn Vnstock trong `AGENTS.md` nếu không có nhu cầu; không sửa cấu hình trợ lý ngoài dự án.

## Bảo toàn dữ liệu và bằng chứng

Các cây được bảo vệ gồm `datasets/`, `trusted_baseline/`, `legacy_version/`, `outputs/`, `output/`, `extensions_C_v1/`, `paper5_research/`, `csonet-paper/`, `reports/`, `logs/`, `reference/`; dữ liệu/model trong `gen_view/`; các config `assets*.json`, `config.py`, `gen_view/xgboost/config.py`; toàn bộ hiện vật/config nghiên cứu trong `experiments_core/`. Lưu danh sách tệp cụ thể ở đầu triển khai; loại `.git`, cache, `.DS_Store`, môi trường ảo và secret khỏi manifest.

- Ghi manifest trước/sau gồm đường dẫn tương đối, kích thước, SHA-256; so cả tập tên tệp để phát hiện thêm/xóa ngoài ý muốn. Tái dùng `sha()` trong `experiments_core/src/frozen.py`.
- Kiểm riêng 181 tệp đã được pin trong `experiments_core/config/frozen_baseline_ref.json`, và manifest gốc của baseline `availability-observed-contract-20261012T233110`. Sai hash có sẵn phải báo là sai lệch trước migration, không tự “sửa baseline”.
- Bảo vệ thêm dataset, bundle và receipt hiện có tại `infra/local/.generated/`; không thu thập `.env` hoặc dump credentials. Kiểm thử migration không ghi vào DB hoặc volume ứng dụng hiện hành.
- Dữ liệu mới chỉ ở `vnstock-migration/gen6/<run-id>/`; bản sao code ở `vnstock-migration/code/`; manifest/contract report ở `vnstock-migration/`. Các đường dẫn này được gitignore trước khi tạo.
- Không copy toàn bộ `outputs/` (~803 MiB tại lúc rà soát); đọc tại chỗ hoặc copy đúng mẫu nhỏ cần đối chiếu. Không đổi quyền/chmod cây dữ liệu gốc.
- Git không bảo vệ đủ dữ liệu ignored: hash trước/sau và output tách riêng là điều kiện bắt buộc. Nếu có tiến trình khác ghi vào cây bảo vệ, xác định người sở hữu và mốc kiểm tra ổn định; không tự dừng/xóa tiến trình.

## Task 1 — Chốt inventory và mốc bảo vệ (không cần key)

**Files:** Chỉ đọc các tệp hiện trạng; sau khi được yêu cầu thực hiện, sửa `.gitignore`, tạo `vnstock-migration/{diagnosis.md,inventory.json,protected-before.json,manifest.json}`.

**Interfaces:** Manifest có mỗi mẫu lời gọi cũ/mới, tham số, tài sản, cửa sổ ngày cố định, file lưu cũ tương ứng, cột join và tình trạng chưa đối chiếu.

- [ ] Ghi nhận Git diff và interpreter/package metadata hiện tại; xác nhận lại image đang chạy thay vì dựa vào trạng thái của lần kiểm tra trước.
- [ ] Rà import/call/config cả tệp ignored liên quan, shell/CI và notebook nếu có mới; phân loại active/archive/direct HTTP. Có thêm active caller thì bổ sung trước khi sửa.
- [ ] Đọc rồi dùng `probe_env.py`/`scan_calls.py` chính thức trong thư mục làm việc nếu cần mở rộng inventory; không chạy mã Vnstock 4.
- [ ] Lập `protected-before.json` và đối chiếu frozen baseline; ghi nguồn đối chiếu có chất lượng khác nhau. CSV VFF trong `datasets/` không được xem là đúng chỉ vì tên file là VFF.
- [ ] Tạo nhánh `codex/vnstock-gen6` tại thời điểm tích hợp phù hợp; sao chép code cần sửa, không sao chép secret, dữ liệu lớn, archive, venv hoặc `.git`.

**Đạt:** Mọi call có vị trí và fixture/baseline hoặc được ghi rõ thiếu đối chứng; không có thay đổi dữ liệu; chưa cần cài hay nhập key.

## Task 2 — Môi trường mới và đầu ra an toàn (không cần key)

**Files:** `requirements.txt`, `requirements-vnstock6.txt`, `crawl/vnstock_io.py`, `tests/software/test_vnstock_crawl_io.py`.

**Interfaces:** `SOURCE = 'fhsc'`; `prepare_output(output: str | Path) -> Path`; `daily_dates(values: pandas.Series) -> pandas.Series` trả chuỗi `YYYY-MM-DD` của ngày Việt Nam. CLI crawler yêu cầu `--output-root`, `--start`, `--end`; khoảng ngày phải hợp lệ. Module import không gọi mạng, tạo thư mục hoặc tải danh sách mã.

- [ ] Viết và chạy test lỗi trước: output ngoài `vnstock-migration/gen6/`, output đã tồn tại, symlink thoát cây và output trỏ vào cây bảo vệ đều bị từ chối trước network/write; ngày sai/đảo khoảng bị từ chối.
- [ ] Thêm test timezone tại ranh giới UTC/Việt Nam; không dùng cắt chuỗi ISO để quyết định ngày khi có timezone.
- [ ] Implement các helper tối thiểu và bỏ singleton có tác dụng phụ khi import. Giữ cách bootstrap `sys.path` theo project root của crawler hiện có để cả `python crawl/stock.py` và `python scripts/fetch_serving_prices.py` import được helper; test bằng subprocess từ working directory khác. Thư mục run mới phải được tạo độc quyền, không tái dùng tên đã tồn tại.
- [ ] Tạo hoặc tái dùng môi trường riêng `~/.venv_6x`; cài `requirements-vnstock6.txt`. Root requirements tham chiếu tệp này; bỏ `vnai`, `vnstock_ezchart` vì không có active import sử dụng chúng. Không thêm `vnstock_chart` thay thế một dependency không được dùng.
- [ ] Chạy `~/.venv_6x/bin/python -m pip check`; xác nhận metadata hai phiên bản, `vnstock version` và `vnstock tools --source fhsc`. Chạy `vnstock status` nếu cần biết quyền sử dụng; không cần key Vnstock cho Market/Reference.
- [ ] Chạy `.venv-software/bin/python -m pytest tests/software/test_vnstock_crawl_io.py -q` với Vnstock được fake/patch tại boundary. Test offline không được yêu cầu cài Vnstock vào `.venv-software`.

**Đạt:** Có môi trường ingestion độc lập và bộ chặn ghi nhầm; chưa truy cập dữ liệu FHSC.

## Task 3 — Cổ phiếu, ETF, VNINDEX và serving pack (code/test không cần key)

**Files:** `crawl/stock.py`, `scripts/fetch_serving_prices.py`, hai test stock/pack; kiểm tra caller `scripts/smoke_market_quant.py`.

**Interfaces:** Giữ các hàm `retrieve_vn30_list()`, `fetch_and_save(symbol)`, `fetch_and_save_index(symbol='VNINDEX')`, `split_train_test(df)`. Thêm `main(argv=None)` có thể test CLI. Stock/index CSV giữ `date,open,high,low,close,volume,symbol`; pack CSV giữ `time,open,high,low,close,volume` và manifest/checksum bên nhập đang dùng.

- [ ] Viết test contract thất bại với fake provider: import mới, `interval='1D'`, `compat='v5'`, khoảng ngày đầy đủ, không âm thầm cắt 100 nến. Nếu cần cap 5.000 để giữ serving contract, dùng `count_back=5000` và báo coverage thực tế, không tuyên bố có đủ lịch sử.
- [ ] Đổi sang `from vnstock import Market, Reference`; `Market(SOURCE).equity(symbol).ohlcv(...)`, `.index(symbol).ohlcv(...)`; nhận diện E1VFVN30 để dùng `.etf(symbol)` theo API được hỗ trợ.
- [ ] Đổi rổ VN30 từ `_ref.index.members('VN30')` sang `Reference(SOURCE).index('VN30').constituents()`, lấy cột `symbol`, kiểm tra mã hợp lệ/không trùng và số lượng dự kiến. Lưu danh sách vào run mới, không thay `datasets/vn30_list.txt`. Đây là rổ tại lúc truy xuất, không phải rổ point-in-time cho 2020.
- [ ] Chuẩn hóa ngày Việt Nam trước split; giữ quy tắc split hiện hành ở cả hai phía, không âm thầm sửa overlap tại SPLIT_DATE trong migration. Test đúng ngày biên, thiếu cột, giá không hợp lệ, ngày trùng xung đột, thứ tự đảo, volume null và nến partial; không tự fill giá hoặc ép null thành 0.
- [ ] Sửa version guard của fetch script thành thế hệ 6; giữ kiểm tra symbols và exclusive output. Lưu provider thực tế, phiên bản, profile, cửa sổ, retrieval time, raw hash và thông tin unit/basis trong manifest. Không gọi CSV đã chuẩn hóa là phản hồi raw của Open API; tách hai loại provenance nếu lưu cả hai.
- [ ] Giá equity OHLCV `v5` đã là nghìn đồng: không chia 1.000 lần nữa; index là điểm. Chỉ ghi `price_basis='provider_adjusted'` khi tài liệu/provenance và đối chiếu nguồn xác nhận. Không giả nhãn chỉ để qua `register_pack()`.
- [ ] Với fixture pack FHSC hợp lệ, kiểm `register_pack()` giữ đơn vị và provenance; monkeypatch `GENERATED` sang `tmp_path` để không ghi catalog thật. Pack không đủ bằng chứng basis phải bị từ chối; không nới guard của caller.
- [ ] Chạy `.venv-software/bin/python -m pytest tests/software/test_vnstock_stock.py tests/software/test_fetch_serving_prices.py -q`.

**Đạt offline:** Các entry point không còn phụ thuộc đời 4, test CSV/manifest/consumer qua; dữ liệu FHSC và độ sâu lịch sử vẫn chờ Task 5 có key.

## Task 4 — Quỹ mở và kiểm tra danh tính (code/test không cần key)

**Files:** `crawl/fund.py`, `tests/software/test_vnstock_fund.py`; chỉ đọc/reuse cách xác minh hiện có ở `phase1_sources.py` khi đối chiếu VFF, không kéo toàn bộ service thành dependency crawler.

**Interfaces:** Giữ `retrieve_fund_list()`, `retrieve_bond_list()`, `get_nav_and_return(symbol)`, `crawl_fund_nav_history()`, `split_train_test(df)`; thêm CLI giống Task 2. CSV tiêu thụ giữ `date,price,symbol`; raw NAV, danh tính, unit và provenance được lưu riêng trong run.

- [ ] Viết test trước cho `ticker` thay `short_name`, phân loại bond theo giá trị thực tế `fund_type`; thiếu/mơ hồ danh tính hoặc loại quỹ phải báo lỗi, không đoán bằng nhãn cũ.
- [ ] Dùng `Reference(SOURCE).fund.list()` và `Reference(SOURCE).fund(symbol).profile()`; dùng `Market(SOURCE).fund(symbol).history(start=..., end=..., compat='v5')` nhận `time/nav`. Không dựa vào alias `.nav()` dù có thể còn được hỗ trợ.
- [ ] Xác nhận ticker/profile và ghi manifest gắn lời gọi với đúng symbol. Nếu bảng NAV không có ticker, giữ liên kết response–request; đối chiếu VFF với hồ sơ VinaCapital/quỹ trái phiếu và nguồn VFF FMarket productId21 đã xác minh. Không áp productId21 cho FHSC vì ID có thể khác hệ thống.
- [ ] Đo và chứng minh đơn vị NAV FHSC trước khi áp `/1000` và làm tròn 2 chữ số. Fake test NAV 26064.61 VND phải ra 26.06; dữ liệu đã là nghìn đồng không được chia lần hai. Không tự suy đoán đơn vị bằng độ lớn giá.
- [ ] Thay bắt chuỗi lỗi `RateLimitExceeded` bằng exception/code thực tế của Vnstock 6; chỉ retry lỗi tạm thời có giới hạn, không retry key sai/thiếu quyền. Không in nguyên vendor exception chứa credential. Lỗi phải tạo exit status thất bại để batch không báo thành công giả.
- [ ] Test hai quỹ có chuỗi khác nhau không bị trả thành cùng chuỗi do gán nhãn, sai ticker bị từ chối, ghi đủ thư mục `full/train/test`, giữ format/split hiện tại và giữ file tốt khi một quỹ thất bại.
- [ ] Chạy `.venv-software/bin/python -m pytest tests/software/test_vnstock_fund.py -q`.

**Đạt offline:** Danh sách quỹ, NAV và export không còn gọi Vnstock 4; xác minh thị trường thật/coverage còn chờ key. Dữ liệu cũ sai không bị sửa hoặc dùng làm chuẩn giá đúng.

## Task 5 — Ba điểm cần người dùng thao tác với FHSC

**Files:** Dữ liệu mới ở `vnstock-migration/gen6/<run-id>/`, báo cáo ở `vnstock-migration/contract-report.md`. Kiểm thử `asset_metadata.py` bằng `MetadataProvider.fetch()` chỉ đọc, không gọi `sync_metadata()` ghi DB.

| Điểm | Người dùng làm | Phần việc được mở khóa |
| --- | --- | --- |
| K1 — Trước API call đầu tiên | Đăng nhập FHSC, tạo API key và tự lưu bằng lệnh bên dưới. Chỉ báo đã lưu hoặc mã lỗi không chứa key | Kiểm tra quyền kết nối và các route FHSC |
| K2 — Trước kiểm thử dữ liệu thật | Không phải gửi lại key; xác nhận key đã có trong môi trường của ingestion | VN30 constituents, cổ phiếu/ETF/VNINDEX OHLCV, danh sách/profile/NAV quỹ, company info |
| K3 — Trước kiểm thử Docker | Tự cung cấp `FHSC_API_KEY` cho môi trường Compose/secret store đang dùng | Kiểm chứng image mới đọc được key và lấy metadata, không ghi DB |

**K1 — Các lệnh do người dùng tự chạy trên Terminal:**

```bash
source ~/.venv_6x/bin/activate
vnstock keys set fhsc
vnstock keys check fhsc
```

- Đăng ký/đăng nhập: <https://invest.fhsc.com.vn/>; tạo khóa: <https://invest.fhsc.com.vn/tai-khoan> → **Quản lý API** (đã xác minh trực tiếp trên giao diện). Vnstock dùng biến `FHSC_API_KEY`; nguồn có thể hiển thị tên `FINHAY_API_KEY`. Không nhập secret vào chat. Không cần API secret cho các thao tác dữ liệu thị trường chỉ đọc được Vnstock tài liệu hóa.
- Key tài khoản Vnstock là loại khác; `Market/Reference` không bắt buộc `vnstock login`. Chỉ hướng dẫn đăng nhập riêng nếu thực tế cần quyền bổ sung, không coi đây là điều kiện lấy OHLCV/NAV.
- Thiếu key: hoàn thành Tasks 1–4 và test offline, dừng trước network capture; đánh dấu “chưa kiểm thử live”, không coi migration hoàn tất.

**K2 — Đối chiếu trực tiếp:**

- [ ] Kiểm tra lần lượt route trên FPT/VCB/HPG, E1VFVN30, VNINDEX, VFF và ít nhất một quỹ khác trong `fund_list.txt`; dùng cửa sổ ngày quá khứ cố định có file đối chứng. Bắt đầu một tháng, sau đó kiểm coverage khung nghiên cứu dài cho từng nhóm tài sản.
- [ ] Lưu nguyên warnings, `df.attrs`, schema, dtypes, timezone, units, row counts, ngày đầu/cuối, thiếu/thừa khóa và max sai lệch sau khi join theo ngày/symbol. Không tắt `SchemaChangeWarning`.
- [ ] Giữ dữ liệu cũ để đối chiếu nguồn/basis. Với VFF, dùng baseline đã xác minh đúng danh tính để kiểm đơn vị; root CSV bị biết là sai chỉ là bằng chứng lịch sử. Nếu các nguồn khác nhau, ghi CHANGED kèm nguyên nhân/bằng chứng; không đòi mọi giá phải giống hoặc làm tròn để ép khớp.
- [ ] Chạy những hàm project đã sửa trên fixture/kết quả mới trong sandbox; bảo đảm downstream đọc được CSV. Không đổi `assets*.json` sang dữ liệu mới và không chạy lại mô hình để thay kết quả luận văn.
- [ ] Nếu FHSC không có đủ NAV/mã/độ sâu lịch sử, báo từng call bị chặn; không bổ sung KBS/FMarket vào chuỗi mới một cách ngầm định. Kế hoạch chỉ hoàn tất khi khoảng thiếu được giải quyết hoặc người dùng chấp thuận phạm vi cụ thể.

**K3 — Docker:** Keyring macOS không tự vào container. Compose hiện đã có `FHSC_API_KEY: ${FHSC_API_KEY:-}` cho `market-metadata-sync`; dùng đúng env file của stack và không in `docker compose config` đầy đủ. Dùng `--no-deps` và override entrypoint sang `vnstock` để chạy `keys check fhsc`, không chạy command sync mặc định. Kiểm tra image/tag thực tế, dependency và `MetadataProvider.fetch('FPT')` trước khi đề xuất chuyển container.

**Đạt live:** Mọi mẫu lời gọi active có kết quả hoặc quyết định được ghi rõ, các sai khác đã được phân loại, key không xuất hiện trong output/report. Không có ghi dữ liệu nghiên cứu hoặc DB ứng dụng.

## Task 6 — Tích hợp, tài liệu, nghiệm thu và rollback

**Files:** Các tệp migration đã liệt kê; `QUICKSTART.md`, `docs/PROJECT_CONTEXT.md`, `docs/software/MARKET_QUANT_BRIDGE.md`; báo cáo `vnstock-migration/report.md` và `protected-after.json`.

- [ ] Áp dụng diff từ bản sao vào nhánh migration sau khi xem diff; không mang theo thay đổi UI/DB đang làm dở của phiên khác. Giữ các pin/build thế hệ 6 đã có, chỉ sửa nếu có chứng cứ lỗi.
- [ ] Cập nhật lệnh chạy mới dùng `~/.venv_6x/bin/python`, bắt buộc output run riêng. Lệnh backtest trên CSV/model hiện tại tiếp tục dùng môi trường nghiên cứu hiện tại; ghi rõ bản lưu trữ đời 4 không còn là hướng dẫn tải dữ liệu.
- [ ] Giữ số liệu và provenance lịch sử trong MARKET_QUANT_BRIDGE; thêm mục migration với lệnh fetch mới, không thay lịch sử KBS 4.0.4 thành FHSC. Không chạy smoke ghi DB/train/approve/publish trong guide như bước kiểm thử mặc định.
- [ ] Chạy bộ test mới và các regression hiện hữu bằng lệnh dưới đây. Test integration DB/container chỉ được chạy trong môi trường disposable, không stack chứa dữ liệu người dùng.

```bash
.venv-software/bin/python -m pytest \
  tests/software/test_vnstock_crawl_io.py \
  tests/software/test_vnstock_stock.py \
  tests/software/test_vnstock_fund.py \
  tests/software/test_fetch_serving_prices.py \
  tests/software/test_asset_metadata_sync.py \
  tests/software/test_data_refresh.py \
  tests/software/test_market_bridge_access.py \
  tests/software/test_snapshot_inputs.py -q
```
- [ ] Lint phạm vi đổi bằng Ruff theo setup hiện tại; test import không có network hoặc write. Kiểm tra `pip check` trong môi trường/image mới, và metadata package thực tế thay vì chỉ đọc requirements.
- [ ] Quét lại active code/config: không còn `vnstock.ui`, guard 4.x, `source='kbs'` trong lời gọi Vnstock, pin `vnai`/`vnstock_ezchart`. Các match trong archives/direct-HTTP/provenance được liệt kê riêng và có lý do giữ.
- [ ] So `protected-after` với `protected-before`, cùng tập tệp/hash và 181 pins baseline. Không chạy `experiments_core.src.run` để “verify” vì hàm freeze có thể ghi lại config; chỉ dùng phần đọc/hash đã xác định.
- [ ] Báo cáo rõ: offline tests, live calls, sai khác KBS/FHSC, coverage NAV, trạng thái key không chứa giá trị, file thay đổi và giới hạn còn lại. Chỉ đánh dấu hoàn tất khi live gates đã đạt hoặc các ngoại lệ đã được người dùng chấp nhận.

**Rollback:** Khôi phục đúng các hunk migration từ nhánh/commit riêng; giữ nguyên thay đổi khác. Giữ môi trường cũ và mọi dữ liệu hiện có; dữ liệu thử mới được giữ riêng để điều tra. Không restore/xóa database, không `docker compose down -v`, không tự xóa venv hoặc cây dữ liệu. Rollback mã không làm Vnstock 4 xác thực trở lại.

## Tiêu chí nghiệm thu

1. Ba entry point active chạy bằng thế hệ 6, không gọi đời 4 và không fallback nguồn ngầm.
2. Rổ VN30, stock/ETF/index OHLCV, quỹ list/profile/NAV và metadata FHSC đều có kiểm thử contract; kiểm thử live ghi nguồn và coverage.
3. Dữ liệu mới không trộn với dữ liệu nghiên cứu; hash và tập tệp trong phạm vi bảo vệ giữ nguyên, frozen baseline không đổi.
4. Consumer pack vẫn kiểm unit/basis/hash đúng; dữ liệu chưa xác minh không được gán `real/provider_adjusted` để qua gate.
5. Không cần gửi key qua chat; các điểm K1/K2/K3 được xử lý trong đúng runtime. Nếu chưa có key hoặc quyền lịch sử, chỉ được báo “sẵn sàng kiểm thử live”, không báo hoàn tất.

## Nguồn chính thức đã đối chiếu

- [Migration và mốc ngừng xác thực](https://vnstocks.com/onboard-member/migration).
- [Skill migration, cập nhật 16/11/2026](https://vnstocks.com/api/skills/migration-assistant/content), [contract check](https://vnstocks.com/api/skills/migration-assistant/reference/contract-check.md), [older → gen6](https://vnstocks.com/api/skills/migration-assistant/reference/older-to-gen6.md), [quy tắc gen5 → gen6](https://vnstocks.com/api/skills/migration-assistant/reference/gen5-to-gen6.md).
- [Market 6.0.1: interval, compat, OHLCV, fund history và units](https://vnstocks.com/docs/vnstock/v6/thi-truong-market).
- [Reference: FHSC constituents, fund ticker/profile và SSI members](https://vnstocks.com/docs/vnstock/v6/tham-chieu-reference).
- [Phạm vi nguồn](https://vnstocks.com/docs/vnstock/v6/tham-khao/nguon-du-lieu), [cài đặt/key/Docker](https://vnstocks.com/docs/vnstock/v6/cai-dat), [FHSC API key](https://developers.fhsc.com.vn/introduction.md).

**Trạng thái khi lập kế hoạch:** Chưa triển khai migration, chưa cài môi trường mới, chưa đọc hoặc kiểm thử key, chưa tạo manifest bảo vệ toàn bộ dữ liệu. Inventory và tài liệu API đã được đọc để lập kế hoạch; các checkbox là việc cần thực hiện sau này.

## Bổ sung ngày 22/11/2026 — Bốn nến VNINDEX có biên độ không hợp lệ

Phản hồi gốc từ FHSC có giá đóng cửa nằm ngoài khoảng `low`–`high` ở bốn phiên bên dưới. OHLC thay thế lấy từ nến ngày DNSE Entrade X và khớp khi tổng hợp nến một phút của DNSE. Giá đóng cửa khớp FHSC trong cả bốn phiên. Crawler giữ khối lượng FHSC vì khối lượng giữa hai nguồn khác nhau. [Phản hồi nến ngày DNSE dùng để đối chiếu](https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from=1613408400&to=1715187600&symbol=VNINDEX&resolution=1D)

| Phiên | Trường thay đổi | FHSC → DNSE (điểm) |
| --- | --- | --- |
| 2021-02-17 | `high` | 1.151,54 → 1.155,78 |
| 2021-12-10 | `open`, `low` | 1.469,83 → 1.470,55 và 1.469,68 → 1.461,78 |
| 2023-05-15 | `low` | 1.067,15 → 1.065,71 |
| 2024-05-06 | `high` | 1.226,89 → 1.241,58 |

Crawler áp dụng bộ OHLC DNSE đã đối chiếu chỉ khi mã là `VNINDEX`, nến bị lỗi và cả ngày giao dịch lẫn bốn giá trị OHLC gốc khớp hồ sơ đã duyệt. Toàn bộ bảng sau đó đi qua validator hiện hành trước khi chia train và test. Trong `manifest.json`, `calls[].replacements` ghi ngày, hai bộ OHLC và nguồn của khối lượng. `calls[].replacement_evidence` ghi URL, thời điểm lấy dữ liệu và SHA-256 của phản hồi DNSE đã lưu.

Nếu còn nến không hợp lệ sau đối chiếu, crawler đánh dấu manifest `failed`, lưu các nến FHSC có biên độ lỗi trong `diagnostics/VNINDEX-ohlc-rejected.json` và trả mã thoát lỗi trước khi xuất CSV VNINDEX.

Chạy lại cùng cửa sổ truy vấn với môi trường Vnstock 6 đã cấu hình FHSC. Chọn một đường dẫn đầu ra mới cho mỗi lần chạy.

```bash
~/.venv_6x/bin/python crawl/stock.py --index VNINDEX \
  --start 2020-01-01 --end 2026-11-21 \
  --output-root vnstock-migration/gen6/vnindex-reconciled-$(date +%Y%m%d-%H%M%S)
```

Lần chạy xác minh ngày 22/11/2026 xuất 1.718 phiên từ 02/01/2020 đến 20/11/2026. Đối chiếu với lần tải FHSC trước đó cho thấy chỉ bốn nến trên đổi OHLC, còn ngày giao dịch, giá đóng cửa và khối lượng khớp ở mọi phiên. SHA-256 của 1.176 tệp nghiên cứu và tham chiếu đều khớp. Kết quả chạy và phản hồi nguồn được lưu cục bộ trong `vnstock-migration/gen6/`.

## Cập nhật thực thi offline — 21/11/2026

Người dùng đã chọn FHSC và cho phép triển khai code/test offline, dừng trước API thật.
Tasks 1–4 và phần offline của Task 6 đã thực hiện; Task 5 chưa chạy theo yêu cầu.
50 test ingestion đạt trong `~/.venv_6x`; regression software/core đạt 911 test,
10 test bỏ qua theo môi trường/cấu hình. Ruff, `pip check` và `git diff --check` qua.
13.874 tệp được bảo vệ không thêm/xóa/đổi nội dung; 181 tệp frozen baseline và
manifest gốc vẫn khớp. Báo cáo và bằng chứng ở `vnstock-migration/report.md`,
`integrity.json` và các manifest before/after trong cùng thư mục ignored.

Đã làm việc trên bản sao rồi áp dụng vào checkout non-main hiện tại, giữ nguyên
thay đổi UI/service có sẵn; chưa chuyển nhánh hay commit. Bộ test ingestion
chạy riêng vì `.venv-software` không có pandas; các test dùng SDK fake và chặn
network, riêng hai test consumer dùng interpreter serving nếu có. Bản sửa sau
review có kiểm tra mã quỹ chứa gạch nối, source/profile bắt buộc, ticker null/sai,
ngày đầy đủ, số liệu không phải boolean và loại quỹ hợp lệ. NAV suy ra đơn vị
đồng chỉ được dùng với đúng hợp đồng đã xác minh của Vnstock 6.0.1.

Chưa xác minh identity, độ phủ lịch sử và giá trị/basis của dữ liệu FHSC thật.
Serving pack vẫn bị consumer từ chối khi basis còn `unverified`; không đổi nhãn
để ép qua gate. Các snapshot nghiên cứu và adapter HTTP trực tiếp vẫn được giữ.
