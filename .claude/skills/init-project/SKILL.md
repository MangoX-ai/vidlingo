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
    ├── transcribe.py       # Whisper local (faster-whisper) — STT engine chính
    ├── requirements.txt    # Python deps (faster-whisper, ctranslate2, requests)
    └── .venv/              # Python virtualenv (cần tạo)
```

> **STT engine chính của dự án là Whisper local** (`faster-whisper`, chạy CPU int8,
> cô lập trong `scripts/.venv`). GPU API ở Bước 6 chỉ là tuỳ chọn tăng tốc — không
> có nó pipeline vẫn chạy đầy đủ bằng Whisper local.

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

## Bước 4 — Whisper local (STT engine chính — ƯU TIÊN)

`faster-whisper` đã được kéo về cùng `requirements.txt` ở Bước 3. Đây là engine
transcribe **mặc định** của dự án, nên BẮT BUỘC verify nó import được trước khi báo xong:

```bash
cd "<PROJECT_ROOT>/scripts"
.venv/bin/python -c "from faster_whisper import WhisperModel; print('✅ Whisper local (faster-whisper) import OK')" \
  || echo "❌ Whisper local lỗi — chạy lại: .venv/bin/pip install -r requirements.txt"
```

Lưu ý về Whisper local:
- Chạy **CPU int8** mặc định — không cần GPU, không cần internet sau khi đã cài.
- **Model tự tải về lần transcribe đầu tiên** (vd `small`) rồi cache lại → lần đầu hơi lâu, các lần sau nhanh.
- `transcribe.py` tự **auto-split** audio > 10 phút thành part 5 phút rồi ghép timestamps.
- Muốn dùng NVIDIA GPU: bỏ comment `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` trong `requirements.txt` rồi cài lại. Thiếu cũng tự fallback CPU — không vỡ pipeline.

## Bước 5 — Tạo thư mục output/

```bash
mkdir -p "<PROJECT_ROOT>/output"
echo "✅ output/ OK"
```

## Bước 6 — Kiểm tra GPU API (TUỲ CHỌN — chỉ để tăng tốc)

Whisper local ở Bước 4 đã đủ để chạy toàn bộ pipeline. GPU API chỉ là phương án
tăng tốc khi có sẵn — **không có cũng không sao**:

```bash
curl -s --max-time 3 http://192.168.1.61:8000/health 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ GPU API OK — model={d[\"model\"]}, device={d[\"device\"]}')" 2>/dev/null \
  || echo "⚠️  GPU API không có — dùng Whisper local (CPU). Pipeline vẫn chạy bình thường."
```

## Báo cáo kết quả

Sau khi xong, hiển thị checklist đầy đủ:

```
✅ yt-dlp vX.X
✅ ffmpeg vX.X
✅ Python venv (scripts/.venv)
✅ Whisper local (faster-whisper) — import OK
✅ output/ folder
✅ GPU API (hoặc ⚠️ không có — dùng Whisper local CPU)

🎉 Dự án đã sẵn sàng!
Bước tiếp theo:
  - Thêm video: /lang-lesson-builder <youtube-url>
  - Mở all-video.html trong trình duyệt để xem
```

## Lưu ý

- `<PROJECT_ROOT>` là thư mục gốc chứa `all-video.html` — hỏi người dùng nếu chưa rõ đường dẫn
- Nếu người dùng dùng **fish shell**: `source .venv/bin/activate.fish` (không phải `source .venv/bin/activate`)
