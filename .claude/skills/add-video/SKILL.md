---
name: add-video
description: Tải video từ YouTube và tự động xử lý transcript + thumbnail. Dùng khi người dùng cung cấp link YouTube, link video bất kỳ, hoặc nói "thêm video", "tải video", "download". Không hỏi lại người dùng — tự chạy toàn bộ pipeline.
---

# Add Video Pipeline

Khi người dùng cung cấp 1 URL (YouTube hoặc bất kỳ platform nào yt-dlp hỗ trợ), chạy toàn bộ pipeline sau **không hỏi lại**.

## Biến môi trường

```
PROJECT_ROOT=/Users/thinhlevan/Downloads/english
OUTPUT_DIR=$PROJECT_ROOT/output
SCRIPTS_DIR=$PROJECT_ROOT/scripts
VENV_PYTHON=$SCRIPTS_DIR/.venv/bin/python3
PART_DURATION=180   # giây mỗi part
```

## Bước 1 — Lấy slug từ title video

```bash
TITLE=$(yt-dlp --get-title "<URL>" 2>/dev/null)
```

Chuyển title thành slug (lowercase, thay space/ký tự đặc biệt bằng `_`, tối đa 60 ký tự):
- Dùng `sed` hoặc Python inline để sanitize
- Ví dụ: `"How To Speak English Well"` → `HowToSpeakEnglishWell`

Nếu URL là YouTube Shorts hoặc không lấy được title, dùng video ID làm slug.

## Bước 2 — Tạo thư mục

```bash
SLUG_DIR=$OUTPUT_DIR/<slug>
mkdir -p "$SLUG_DIR/parts"
```

## Bước 3 — Tải video + thumbnail

Tải video và thumbnail cùng lúc — không cần generate thumb bằng ffmpeg nữa.

```bash
yt-dlp \
  --format "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
  --merge-output-format mp4 \
  --write-thumbnail \
  --convert-thumbnails jpg \
  --output "$SLUG_DIR/video.%(ext)s" \
  --output "thumbnail:$SLUG_DIR/thumb.%(ext)s" \
  --no-playlist \
  "<URL>"
```

Kết quả: `video.mp4` + `thumb.jpg` trong `$SLUG_DIR`.

Nếu `video.mp4` đã tồn tại (> 0 bytes): bỏ qua, dùng file cũ.

## Bước 4 — Tách parts (180 giây mỗi part)

```bash
ffmpeg -i "$SLUG_DIR/video.mp4" \
  -c copy \
  -f segment \
  -segment_time 180 \
  -reset_timestamps 1 \
  "$SLUG_DIR/parts/part_%03d.mp4"
```

## Bước 5 — Transcribe từng part

Lấy danh sách parts:
```bash
ls "$SLUG_DIR/parts"/part_*.mp4 | sort
```

Với mỗi `part_NNN.mp4`:
```bash
$VENV_PYTHON $SCRIPTS_DIR/transcribe.py \
  "$SLUG_DIR/parts/part_NNN.mp4" \
  --language en \
  > "$SLUG_DIR/parts/part_NNN_transcript.json" \
  2> "$SLUG_DIR/parts/part_NNN.log"
```

Chạy tuần tự từng part (không song song) để tránh OOM. Log progress cho người dùng biết đang xử lý part nào.

## Bước 6 — Báo kết quả

Hiển thị:

- Slug: `<slug>`
- Đường dẫn: `output/<slug>/`
- Số parts đã transcript: N/N
- Nhắc người dùng chạy `node deployment/deploy.js` để deploy lên R2

## Xử lý lỗi

- Nếu `yt-dlp` thất bại: báo lỗi và dừng
- Nếu 1 part transcript lỗi: ghi log, tiếp tục các part còn lại, báo cáo cuối
- Nếu `ffmpeg` segment lỗi: thử tải lại hoặc dừng với thông báo rõ ràng

## Lưu ý ngôn ngữ

Mặc định `--language en` cho video tiếng Anh. Nếu người dùng đề cập video tiếng Việt, dùng `--language vi`.
