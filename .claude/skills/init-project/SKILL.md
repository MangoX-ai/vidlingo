---
name: init-project
description: Setup toàn bộ môi trường cho dự án học tiếng Anh. Dùng khi khách hàng mới clone dự án, báo lỗi "command not found", thiếu dependency, hoặc hỏi "cài gì", "setup như thế nào", "bắt đầu từ đâu". Tự động kiểm tra và cài từng thành phần cần thiết.
---

# Init Project — Setup Môi Trường

Chạy tuần tự từng bước, kiểm tra xem đã cài chưa trước khi cài để tránh cài lại thứ đã có.

## Cấu trúc dự án

```
english/
├── all-video.html          # UI chính
├── output/                 # Video + transcripts (<slug>/video.mp4 ...)
└── scripts/
    ├── transcribe.py       # Transcribe local (CPU)
    ├── gen_thumbnails.py   # Generate thumb từ video
    ├── requirements.txt    # Python deps
    └── .venv/              # Python virtualenv (cần tạo)
```

## Bước 1 — Kiểm tra hệ thống

```bash
echo "OS: $(uname -s)"
python3 --version 2>/dev/null || echo "❌ Python3 chưa cài"
yt-dlp --version 2>/dev/null || echo "❌ yt-dlp chưa cài"
ffmpeg -version 2>/dev/null | head -1 || echo "❌ ffmpeg chưa cài"
```

Báo kết quả checklist rõ ràng cho người dùng biết thứ nào thiếu.

## Bước 2 — Cài system tools còn thiếu

**macOS** (dùng Homebrew):
```bash
# Kiểm tra brew
which brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# yt-dlp
which yt-dlp || brew install yt-dlp

# ffmpeg
which ffmpeg || brew install ffmpeg
```

**Linux** (Ubuntu/Debian):
```bash
# yt-dlp
which yt-dlp || pip3 install yt-dlp

# ffmpeg
which ffmpeg || sudo apt-get install -y ffmpeg
```

**Windows** — hướng dẫn người dùng:
- yt-dlp: `winget install yt-dlp.yt-dlp` hoặc tải từ https://github.com/yt-dlp/yt-dlp/releases
- ffmpeg: `winget install Gyan.FFmpeg` hoặc tải từ https://ffmpeg.org/download.html

## Bước 3 — Setup Python venv cho scripts/

```bash
SCRIPTS_DIR=<PROJECT_ROOT>/scripts

cd "$SCRIPTS_DIR"

# Tạo venv nếu chưa có
if [ ! -d ".venv" ]; then
  echo "📦 Tạo Python venv..."
  python3 -m venv .venv
fi

# Cài dependencies
echo "📦 Cài Python packages..."
.venv/bin/pip install -r requirements.txt --quiet
echo "✅ Python venv OK"
```

> Trên Windows dùng `.venv\Scripts\pip` thay vì `.venv/bin/pip`

## Bước 4 — Tạo thư mục output/

```bash
mkdir -p "<PROJECT_ROOT>/output"
echo "✅ output/ OK"
```

## Bước 5 — Kiểm tra GPU API (tuỳ chọn)

GPU API dùng để transcribe nhanh hơn so với CPU local:
```bash
curl -s http://192.168.1.61:8000/health 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ GPU API OK — model={d[\"model\"]}, device={d[\"device\"]}')" 2>/dev/null \
  || echo "⚠️  GPU API không có — sẽ dùng CPU (chậm hơn)"
```

Nếu không có GPU API, `add-video` skill dùng `scripts/transcribe.py` local với CPU — vẫn hoạt động bình thường.

## Báo cáo kết quả

Sau khi xong, hiển thị checklist đầy đủ:

```
✅ yt-dlp vX.X
✅ ffmpeg vX.X
✅ Python venv (scripts/.venv)
✅ output/ folder
✅ GPU API (hoặc ⚠️ không có — dùng CPU)

🎉 Dự án đã sẵn sàng!
Bước tiếp theo:
  - Thêm video: /add-video <youtube-url>
  - Mở all-video.html trong trình duyệt để xem
```

## Lưu ý

- `<PROJECT_ROOT>` là thư mục gốc chứa `all-video.html` — hỏi người dùng nếu chưa rõ đường dẫn
- Nếu người dùng dùng **fish shell**: `source .venv/bin/activate.fish` (không phải `source .venv/bin/activate`)
