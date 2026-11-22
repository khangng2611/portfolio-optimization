# Demo kín trên VPS bằng Docker Compose và SSH tunnel

Release `v0.1.0-demo.1`, chuẩn bị ngày 11/11/2026. Dùng VPS riêng, Ubuntu 24.04
LTS amd64, 4 vCPU, RAM 8 GB, SSD 80 GB làm cấu hình khởi điểm cho ít người.
Cấu hình phần cứng này cần được đo lại khi chạy tải thực tế.

Phạm vi nghiệm thu là đăng nhập, hồ sơ rủi ro, danh mục DEMO, EW/MVO, chấp nhận
phương án và mở lại lịch sử sau restart. Bản nguồn gồm Auth nội bộ, Chat,
Knowledge và hỗ trợ Phase 1 hiện có. Dữ liệu giá thật, model offline, corpus đã
index và tài khoản trên máy phát triển cần quy trình chuẩn bị riêng trên VPS.

Tái sử dụng `infra/local/compose.yaml` và `scripts/setup_software.py`. Browser
truy cập `http://localhost:3000` qua SSH. Web, API và hạ tầng chỉ publish lên
loopback của VPS. Mỗi VPS tạo credentials và volume mới. Các script smoke giữ
Compose project `portfolio-auth-demo`, nên dùng một bản cài trên mỗi VPS.

## 1. Chuẩn bị VPS

Tạo user `deploy` có SSH public key, quyền sudo và quyền chạy Docker. Xác minh
host fingerprint khi SSH lần đầu. Trong firewall của nhà cung cấp, chỉ cho
phép SSH từ IP quản trị, áp dụng cho cả IPv4 và IPv6. Giữ phiên SSH hiện có
trong lúc thử một kết nối SSH mới sau khi thay firewall.

Cài Docker Engine từ apt repository chính thức theo
[hướng dẫn Ubuntu của Docker](https://docs.docker.com/engine/install/ubuntu/).
Chọn Engine **28 trở lên**, cùng Buildx và Compose plugin. Docker trước 28 có
trường hợp máy cùng mạng L2 truy cập được cổng publish lên localhost.
[Tài liệu port publishing](https://docs.docker.com/engine/network/port-publishing/).

Chạy trên VPS với user `deploy` sau khi Docker đã hoạt động.

```bash
sudo apt-get update
sudo apt-get install -y git python3.12 python3.12-venv openssl curl ca-certificates xz-utils libgomp1
docker info >/dev/null
docker compose version
python3.12 --version
docker version --format '{{.Server.Version}}' | python3.12 -c \
  'import sys; assert int(sys.stdin.read().split(".")[0]) >= 28, "Docker Engine >=28 required"'
test "$(dpkg --print-architecture)" = amd64
df -h /
free -h
```

Cài Node 22 từ binary chính thức. Phiên bản dưới đây khớp runtime đã dùng để
kiểm tra release. Dừng nếu tải tệp hoặc kiểm tra SHA-256 thất bại.

```bash
set -euo pipefail
node_setup_dir=$(mktemp -d)
cd "$node_setup_dir"
curl --fail --show-error --location --remote-name https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.xz
curl --fail --show-error --location --remote-name https://nodejs.org/dist/v22.22.2/SHASUMS256.txt
awk '$2 == "node-v22.22.2-linux-x64.tar.xz"' SHASUMS256.txt > node.sha256
test -s node.sha256
sha256sum --check node.sha256
sudo tar -xJf node-v22.22.2-linux-x64.tar.xz --strip-components=1 -C /usr/local
node --version
npm --version
cd ~
```

VPS cần outbound HTTPS để tải image, dependency và nguồn pgvector lúc build.
Trong cấu hình demo mặc định, workers không nhận provider key hoặc paid overlay.

## 2. Chuyển đúng release đã commit

Dùng Git bundle để chuyển release local qua SSH, kể cả khi tag chưa được push.
Chạy trên máy phát triển, tại checkout chứa tag release.

```bash
set -euo pipefail
release=v0.1.0-demo.1
test -z "$(git status --porcelain --untracked-files=all)"
git rev-parse "$release^{commit}"
mkdir -p output/releases
git bundle create "output/releases/portfolio-$release.bundle" "refs/tags/$release"
git bundle verify "output/releases/portfolio-$release.bundle"
shasum -a 256 "output/releases/portfolio-$release.bundle"
scp "output/releases/portfolio-$release.bundle" deploy@VPS_IP:~/
```

Thay `VPS_IP` bằng IP thật. Ghi lại SHA commit và SHA-256 của bundle từ máy phát
triển để đối chiếu trên VPS. Bundle chứa mã nguồn và lịch sử Git đến release.
Các thư mục ignored như `.generated`, output và provider env nằm ngoài bundle.

Trên VPS, kiểm tra hash rồi clone vào thư mục trống.

```bash
set -euo pipefail
release=v0.1.0-demo.1
sha256sum "$HOME/portfolio-$release.bundle"
# Đối chiếu hash với máy phát triển trước khi tiếp tục.
git clone --branch "$release" "$HOME/portfolio-$release.bundle" "$HOME/portfolio-demo"
cd "$HOME/portfolio-demo"
git switch --detach "$release"
git rev-parse HEAD
test -z "$(git status --porcelain --untracked-files=all)"
```

Đối chiếu `git rev-parse HEAD` với SHA đã ghi. Dùng cùng checkout này cho các
lệnh vận hành tiếp theo để giữ đúng đường dẫn bind mount và credentials.

## 3. Chuẩn bị và dựng stack trên VPS

Các lệnh trong phần này chạy tại `~/portfolio-demo`. Setup CLI tạo môi trường
Python riêng, cài Web dependencies và sinh config. Khi chạy lại, CLI giữ secrets
và volume hiện có. Tạo môi trường mới từ credentials của chính VPS.

```bash
set -euo pipefail
cd ~/portfolio-demo
umask 077
python3.12 scripts/setup_software.py prepare --python python3.12 --refresh-demo
python3.12 scripts/check_private_demo.py --release v0.1.0-demo.1
python3.12 scripts/setup_software.py up --python python3.12 --skip-install
```

Lệnh kiểm tra yêu cầu HEAD đúng release, checkout sạch, các cổng publish có
loopback rõ ràng, origin đúng `http://localhost:3000` và provider chưa cấu hình.
Nó đọc Compose qua pipe, chỉ in kết luận. Kiểm tra tiếp trạng thái runtime.

```bash
dc() { docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml "$@"; }
dc config --quiet
dc ps -a
curl --fail --silent --show-error http://127.0.0.1:3000/health/live
curl --fail --silent --show-error http://127.0.0.1:8001/health/ready
curl --fail --silent --show-error http://127.0.0.1:8002/health/ready
git rev-parse HEAD > infra/local/.generated/release-commit.txt
dc images --format json > infra/local/.generated/release-images.json
```

API và hạ tầng có healthcheck cần đạt healthy. Dispatch/consume workers có thể
chỉ hiện running. Các container `*-migrate` phải kết thúc thành công với exit
code 0. Receipt image giúp ghi nhận build thực tế vì base-image tags và package
repositories có thể thay đổi dù source commit giữ nguyên.

## 4. Kiểm tra API và kết quả sau restart

Các smoke dưới đây tạo danh mục, job, snapshot và target DEMO trong DB của VPS.
Boundary probe tạo rồi xóa các bảng kiểm tra quyền tạm thời. Chạy trước buổi demo.

```bash
set -euo pipefail
.venv-software/bin/python infra/local/verify_boundaries.py
.venv-software/bin/python scripts/smoke_software.py
.venv-software/bin/python scripts/smoke_g2.py
dc restart auth-api web portfolio-api portfolio-consume portfolio-dispatch \
  quant-api quant-consume quant-dispatch quant-publication \
  market-api market-consume market-dispatch
dc up -d --wait --wait-timeout 240
.venv-software/bin/python scripts/smoke_software.py --verify-receipt
.venv-software/bin/python scripts/smoke_g2.py --verify-receipt
```

Chỉ nghiệm thu khi tất cả lệnh đều PASS. Các kiểm tra đối chiếu cùng recommendation,
input hash, lịch sử, quyền sở hữu và accepted target đã ghi trước restart.
Lỗi freshness cần làm mới DEMO bằng bước 7, rồi chạy lại các smoke để tạo receipt
cho lượt nghiệm thu mới.

## 5. Mở SSH tunnel từ máy cá nhân

Cổng 3000 trên máy cá nhân cần trống. Nếu đang chạy Web local, dừng riêng Web đó
hoặc dùng một máy cá nhân khác. Mở terminal riêng và giữ kết nối này trong suốt
buổi demo.

```bash
ssh -N -T \
  -L 127.0.0.1:3000:127.0.0.1:3000 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  deploy@VPS_IP
```

Truy cập **http://localhost:3000**. Giữ hostname và port này để Origin, session
và CSRF khớp cấu hình BFF. SSH chuyển traffic đến loopback VPS qua kênh mã hóa.
[Tài liệu OpenSSH](https://man.openbsd.org/ssh.1).

Trên máy cá nhân, thử riêng `http://VPS_IP:3000` với timeout 5 giây và xác nhận
không nhận được HTTP response. Kiểm tra tương tự các cổng 8001–8006, 5433, 5673,
6380 và 15673. Nếu VPS có IPv6 public, kiểm tra cả địa chỉ IPv6. Khi ngắt tunnel,
browser không được tải mới dữ liệu từ ứng dụng. Mỗi người xem cần SSH key và
tunnel riêng, cùng tài khoản ứng dụng riêng.

## 6. Kiểm tra luồng trên browser

Xem credentials của `alice` và `bob` trực tiếp trong SSH terminal tin cậy bằng
`less infra/local/.generated/accounts.json`. Giữ tệp này trên VPS và tránh đưa
màn hình credentials vào bản ghi demo.

1. Đăng nhập `alice`, hoàn tất hồ sơ rủi ro, tạo danh mục với universe `DEMO`.
2. Tạo đề xuất EW. Kiểm tra ba tài sản giả lập, tổng tỷ trọng 100% và nhãn DEMO.
3. Tạo đề xuất MVO. Xác nhận yêu cầu, chờ job hoàn thành và xem nguồn dữ liệu.
4. Chấp nhận một đề xuất. Kiểm tra accepted target và lịch sử danh mục, rồi reload.
5. Mở cửa sổ riêng tư, đăng nhập `bob`, thử URL danh mục của `alice`. Bob phải
   không xem được danh mục hoặc đề xuất của Alice.
6. Chạy lại đoạn restart ở bước 4. Với browser của Alice, mở lại đúng danh mục
   và kiểm tra accepted target, phân bổ và lịch sử đã lưu.
7. Đăng xuất, tải lại trang, xác nhận session đã kết thúc.

Tùy chọn kiểm tra tự động trên chính VPS. Các test này tạo thêm dữ liệu DEMO và
thao tác fixture trên stack dùng riêng cho demo.

```bash
cd ~/portfolio-demo/apps/web
npx --no-install playwright install --with-deps chromium
E2E_DISPOSABLE_STACK=1 npm run test:browser
cd ../..
dc restart auth-api web portfolio-api portfolio-consume portfolio-dispatch \
  quant-api quant-consume quant-dispatch quant-publication market-api market-consume market-dispatch
dc up -d --wait --wait-timeout 240
cd apps/web
E2E_DISPOSABLE_STACK=1 npm run test:browser:persistence
```

Nếu `--with-deps` yêu cầu quyền cài package hệ thống, chạy riêng
`sudo env "PATH=$PATH" npx --no-install playwright install-deps chromium`, rồi
chạy `npx --no-install playwright install chromium` dưới user `deploy`.

## 7. Chuẩn bị trước mỗi buổi demo

Bundle DEMO hết hạn sau một ngày. Chạy từ `~/portfolio-demo` để xuất bundle và
CSV mới bất biến, giữ các dữ liệu và bundle cũ.

```bash
cd ~/portfolio-demo
python3.12 infra/local/bootstrap.py --refresh-demo
python3.12 scripts/check_private_demo.py --release v0.1.0-demo.1
.venv-software/bin/python scripts/smoke_software.py
.venv-software/bin/python scripts/smoke_g2.py
```

Refresh catalog được các adapter đọc lại mà không cần restart. Các đề xuất đã
hoàn thành vẫn ở trong lịch sử. Việc tạo đề xuất mới dùng input đang còn hạn.

Nếu có lỗi, kiểm tra `dc ps -a`, `docker stats --no-stream`, dung lượng đĩa và
log service liên quan ngay trên VPS. Log và config có thể chứa thông tin riêng,
nên lọc trước khi chia sẻ. Khi `setup` dừng giữa chừng, khắc phục nguyên nhân
rồi chạy lại cùng lệnh `up` trên cùng checkout.

## 8. Dừng và giữ bản demo

`dc stop` dừng ứng dụng và giữ container/volume. `dc start` bật lại container đã
có. Chạy `dc up -d --wait --wait-timeout 240` để kiểm tra sẵn sàng khi khởi động.
Giữ nguyên `.generated` cùng các named volumes để các credentials, bundle và
dữ liệu khớp nhau. `down -v` sẽ xóa volume chứa dữ liệu demo.

Trước khi nâng sang release khác, tắt stack và tạo snapshot toàn bộ đĩa VPS,
gồm Docker volumes và checkout với `.generated`. Phục hồi cả snapshot nếu cần
quay lại sau migration. Giữ bản release này trong checkout cố định trong suốt
buổi demo.

## Điều kiện nghiệm thu trên VPS

- [ ] SHA commit và checksum bundle khớp máy phát triển, checkout sạch.
- [ ] Docker Engine >=28, mọi cổng ứng dụng chỉ bind loopback.
- [ ] Migration exit 0, API/hạ tầng healthy và các workers running.
- [ ] Boundary, MVO/Market smoke và G2 smoke đều PASS.
- [ ] Đối chiếu cùng receipts sau restart đều PASS.
- [ ] Browser qua SSH hoàn thành luồng đăng nhập, EW/MVO, accept và lịch sử.
- [ ] Bob bị chặn truy cập dữ liệu Alice.
- [ ] Địa chỉ public IPv4/IPv6 không phục vụ các cổng ứng dụng.

Kết quả kiểm tra trên máy phát triển được ghi trong `PRIVATE_VPS_RELEASE.md`.
Các checkbox trên dành cho lần nghiệm thu thực tế trên VPS.
