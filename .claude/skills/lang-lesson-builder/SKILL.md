---
name: lang-lesson-builder
description: Tải video từ YouTube và tự động xử lý transcript + thumbnail. Dùng khi người dùng cung cấp link YouTube, link video bất kỳ, hoặc nói "thêm video", "tải video", "download". Không hỏi lại người dùng — tự chạy toàn bộ pipeline.
---

# Add Video Pipeline

Khi người dùng cung cấp 1 URL (YouTube hoặc bất kỳ platform nào yt-dlp hỗ trợ), chạy toàn bộ pipeline sau **không hỏi lại**.

## Biến môi trường

```
PROJECT_ROOT=<thư mục gốc chứa all-video.html>   # vd: /Users/vudinh/Development/hoc-ngoai-ngu/hoc-tieng-nuoc-ngoai
OUTPUT_DIR=$PROJECT_ROOT/output
SCRIPTS_DIR=$PROJECT_ROOT/scripts
VENV_PYTHON=$SCRIPTS_DIR/.venv/bin/python3
PART_DURATION=180   # giây mỗi part (chỉ dùng cho fallback Whisper)
```

> `PROJECT_ROOT` là thư mục chứa `all-video.html` — KHÔNG hardcode máy người khác.
> Nếu chưa rõ, tìm bằng `all-video.html` trong workspace hiện tại.

## Chiến lược transcript: YouTube caption trước, Whisper local sau

1. **Ưu tiên**: tải auto-caption ngôn ngữ gốc của YouTube (`*-orig`, định dạng `json3`)
   rồi convert sang schema chung bằng `scripts/yt_transcript.py`. Nhanh, không tốn CPU,
   không bị hallucination, tên riêng chính xác hơn.
2. **Fallback**: nếu video không có auto-caption gốc (ngôn ngữ hiếm, creator tắt caption,
   hoặc platform khác YouTube) → mới chạy `scripts/transcribe.py` (Whisper local) per-part.

Cả 2 nhánh đều xuất ra cùng schema `{text, duration, words, segments, source}` trong
`parts/*_transcript.json`, nên `all-video.html` đọc giống hệt nhau.

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

## Bước 4 — Ưu tiên: lấy transcript từ YouTube (auto-caption gốc)

Thử tải auto-caption ngôn ngữ gốc (`*-orig`) rồi convert. Thành công thì `USE_YT_CAPTION=1`
và BỎ QUA hẳn Bước 5 (Whisper). `yt_transcript.py` chỉ dùng stdlib nên `python3` thường
cũng chạy, nhưng dùng `$VENV_PYTHON` cho chắc.

```bash
USE_YT_CAPTION=0

yt-dlp --no-playlist --skip-download \
  --write-auto-subs --sub-langs ".*-orig" --sub-format json3 \
  --output "$SLUG_DIR/yt_orig" "<URL>" 2>/dev/null

ORIG_JSON=$(ls "$SLUG_DIR"/yt_orig*.json3 2>/dev/null | head -1)
if [ -n "$ORIG_JSON" ] && \
   $VENV_PYTHON "$SCRIPTS_DIR/yt_transcript.py" "$ORIG_JSON" \
     > "$SLUG_DIR/parts/part_000_transcript.json" \
     2> "$SLUG_DIR/parts/yt_caption.log"; then
  USE_YT_CAPTION=1
  echo "✅ Dùng transcript YouTube ($(basename "$ORIG_JSON")) — bỏ qua Whisper"
else
  rm -f "$SLUG_DIR/parts/part_000_transcript.json"
  echo "⚠️  Không có/parse được caption gốc — fallback Whisper local"
fi
```

> Caption phủ toàn bộ video (timestamp tuyệt đối từ 0) → ghi thành 1 file
> `parts/part_000_transcript.json`. `all-video.html` đọc thư mục `parts/` và cộng dồn
> `duration` từng file, nên 1 file = cả video vẫn đúng. KHÔNG cần tách part mp4 ở nhánh này.

## Bước 5 — Fallback: Whisper local (CHỈ khi không có caption YouTube)

Bỏ qua hoàn toàn nếu `USE_YT_CAPTION=1`.

```bash
if [ "$USE_YT_CAPTION" = "0" ]; then
  # 5a — Tách parts (180s mỗi part) để tránh OOM khi transcribe
  ffmpeg -i "$SLUG_DIR/video.mp4" \
    -c copy -f segment -segment_time "$PART_DURATION" -reset_timestamps 1 \
    "$SLUG_DIR/parts/part_%03d.mp4" -y

  # 5b — Transcribe TUẦN TỰ từng part (không song song, tránh OOM)
  for p in "$SLUG_DIR/parts"/part_*.mp4; do
    name=$(basename "$p" .mp4)
    echo "▶️  Whisper: $name ..."
    $VENV_PYTHON "$SCRIPTS_DIR/transcribe.py" "$p" --language en \
      > "$SLUG_DIR/parts/${name}_transcript.json" \
      2> "$SLUG_DIR/parts/${name}.log"
  done
fi
```

Mặc định `--language en`. Video tiếng Việt → `--language vi` (xem "Lưu ý ngôn ngữ").

## Bước 6 — Sinh câu hỏi Listening chuẩn IELTS (AI agent)

Sau khi transcript đã xong, AI agent (chính bạn — không gọi API ngoài) ĐỌC TOÀN BỘ nội dung
transcript rồi tự soạn **~10 câu hỏi luyện nghe theo chuẩn IELTS Listening**, lưu ra
`output/<slug>/ielts_listening.json`.

**1. Gộp toàn bộ text transcript để đọc** (cả 2 nhánh đều nằm trong `parts/*_transcript.json`):

```bash
$VENV_PYTHON -c "
import json, glob
parts = sorted(glob.glob('$SLUG_DIR/parts/*_transcript.json'))
out = []
for f in parts:
    d = json.load(open(f))
    for s in d.get('segments', []):
        if s.get('text','').strip():
            out.append(f\"[{s['start']:.1f}s] {s['text'].strip()}\")
print('\n'.join(out))
"
```

Đọc kỹ output (mỗi dòng có timestamp `[12.3s]` để gắn vào câu hỏi).

**2. Soạn câu hỏi** — bám sát dạng đề IELTS Listening, trộn nhiều dạng cho đủ ~10 câu:

- **Multiple choice** (A/B/C) — 3–4 câu
- **Sentence / Note completion** — 3 câu, có giới hạn từ (`word_limit`), vd `"NO MORE THAN TWO WORDS AND/OR A NUMBER"`. Đáp án phải là **đúng từ xuất hiện trong transcript**.
- **Short-answer** — 2 câu, đáp án ngắn lấy trực tiếp từ audio.
- **Matching / Multiple choice (gist hoặc suy luận)** — 1–2 câu.

Nguyên tắc chuẩn IELTS:
- Câu hỏi phải **trả lời được hoàn toàn từ nội dung audio** — không hỏi kiến thức ngoài.
- Dùng **paraphrase** (diễn đạt lại) trong câu hỏi thay vì lặp y nguyên câu trong transcript — đây là điểm cốt lõi IELTS.
- Sắp theo **thứ tự xuất hiện** trong video (như đề thật).
- Mỗi câu kèm `time` (giây) chỗ nghe được đáp án + `explanation` ngắn trích câu gốc.

**3. Ghi file** `output/<slug>/ielts_listening.json` theo schema:

```json
{
  "slug": "<slug>",
  "source_transcript": "youtube:json3 | faster-whisper",
  "level": "IELTS Listening",
  "total": 10,
  "questions": [
    {
      "no": 1,
      "type": "multiple_choice",
      "question": "What is the Coral Board mainly designed for?",
      "options": ["A. Cloud training", "B. On-device AI", "C. Web hosting"],
      "answer": "B. On-device AI",
      "word_limit": null,
      "time": 1.5,
      "explanation": "\"built for on-device AI ... machine learning accelerator inside\""
    },
    {
      "no": 2,
      "type": "sentence_completion",
      "question": "The board is small, low power and built for developers to ____ on embedded devices.",
      "options": [],
      "answer": "experiment",
      "word_limit": "ONE WORD ONLY",
      "time": 8.0,
      "explanation": "\"built for developers to experiment with on embedded devices\""
    }
  ]
}
```

> `type` ∈ `multiple_choice | sentence_completion | note_completion | short_answer | matching`.
> Nếu transcript quá ngắn (< ~80 từ) thì soạn ít hơn 10 câu cũng được — báo rõ số câu thực tế.
> Ghi file bằng Write tool, không cần script riêng.

## Bước 7 — Báo kết quả

Hiển thị:

- Slug: `<slug>`
- Đường dẫn: `output/<slug>/`
- Nguồn transcript: **YouTube caption** (`source: youtube:json3`) hay **Whisper local** (`faster-whisper:*`)
- Số file transcript: N (caption = 1 file; Whisper = số part)
- Câu hỏi IELTS: đã sinh N câu → `output/<slug>/ielts_listening.json`
- Nhắc người dùng mở `all-video.html` trong trình duyệt để xem (chạy local, không deploy)

## Xử lý lỗi

- Nếu `yt-dlp` (tải video) thất bại: báo lỗi và dừng
- Caption YouTube không có/parse lỗi: KHÔNG phải lỗi — tự fallback Whisper local (Bước 5)
- Nếu 1 part Whisper lỗi: ghi log, tiếp tục các part còn lại, báo cáo cuối
- Nếu `ffmpeg` segment lỗi: thử tải lại hoặc dừng với thông báo rõ ràng

## Lưu ý ngôn ngữ

- **Caption YouTube** tự đúng ngôn ngữ gốc nhờ `--sub-langs ".*-orig"` (lấy bản `-orig`,
  KHÔNG lấy bản dịch máy như `vi` trên video tiếng Anh) — không cần chỉ định ngôn ngữ.
- **Whisper fallback**: mặc định `--language en`. Video tiếng Việt → đổi sang `--language vi`.
