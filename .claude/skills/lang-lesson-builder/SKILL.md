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

Cả 2 nhánh đều xuất ra cùng schema `{text, duration, segments, source}` trong
`parts/*_transcript.json`, nên `all-video.html` đọc giống hệt nhau.
(Scripts KHÔNG còn xuất `words[]` — app chỉ đọc `segments` + `duration`.)

## Chế độ phát: YouTube iframe (không tải video) vs MP4 local

- **YouTube + có caption gốc** → **YouTube-only**: KHÔNG tải `video.mp4`, app phát qua
  **YouTube IFrame** nhờ field `youtube_id` trong `ielts_listening.json`. Tiết kiệm vài trăm
  MB mỗi clip. (app phải mở qua `http://localhost...`, KHÔNG chạy `file://` — iframe YouTube
  chặn origin `null`.)
- **Nền tảng khác / YouTube không có caption** → vẫn **tải `video.mp4`** và phát bằng `<video>`
  native (vì các nền tảng khác không có JS Player API để tua đúng đoạn câu hỏi, và nhánh
  Whisper cần file audio để bóc băng).

## Bước 1 — Lấy slug từ title video

```bash
TITLE=$(yt-dlp --get-title "<URL>" 2>/dev/null)
```

Chuyển title thành slug (lowercase, thay space/ký tự đặc biệt bằng `_`, tối đa 60 ký tự):
- Dùng `sed` hoặc Python inline để sanitize
- Ví dụ: `"How To Speak English Well"` → `HowToSpeakEnglishWell`

Nếu URL là YouTube Shorts hoặc không lấy được title, dùng video ID làm slug.

**Trích YouTube ID** (để quyết định chế độ phát ở Bước 3-4):

```bash
YT_ID=$(yt-dlp --no-playlist --print "%(id)s" "<URL>" 2>/dev/null)
EXTRACTOR=$(yt-dlp --no-playlist --print "%(extractor)s" "<URL>" 2>/dev/null)
IS_YOUTUBE=0; [ "$EXTRACTOR" = "youtube" ] && IS_YOUTUBE=1
echo "YT_ID=$YT_ID | IS_YOUTUBE=$IS_YOUTUBE"
```

## Bước 2 — Tạo thư mục

```bash
SLUG_DIR=$OUTPUT_DIR/<slug>
mkdir -p "$SLUG_DIR/parts"
```

## Bước 3 — Lấy transcript (YouTube caption TRƯỚC)

Thử caption gốc **trước khi tải media** — vì nếu là YouTube + có caption thì ta khỏi tải video.
Thành công thì `USE_YT_CAPTION=1` và BỎ QUA hẳn Whisper (Bước 5).

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
rm -f "$SLUG_DIR"/yt_orig*.json3   # dọn file json3 thô

# Cờ quyết định chế độ phát: YouTube + có caption → KHÔNG tải video, dùng iframe.
YOUTUBE_ONLY=0
[ "$IS_YOUTUBE" = "1" ] && [ "$USE_YT_CAPTION" = "1" ] && YOUTUBE_ONLY=1
echo "YOUTUBE_ONLY=$YOUTUBE_ONLY"
```

> Caption phủ toàn bộ video (timestamp tuyệt đối từ 0) → ghi thành 1 file
> `parts/part_000_transcript.json`. `all-video.html` đọc thư mục `parts/` và cộng dồn
> `duration` từng file, nên 1 file = cả video vẫn đúng. KHÔNG cần tách part mp4 ở nhánh này.

## Bước 4 — Tải media (tuỳ chế độ)

**Nhánh YouTube-only** (`YOUTUBE_ONLY=1`): CHỈ tải thumbnail, **KHÔNG tải `video.mp4`**.
App phát qua iframe nhờ `youtube_id` (ghi ở Bước 6).

```bash
if [ "$YOUTUBE_ONLY" = "1" ]; then
  yt-dlp --no-playlist --skip-download --write-thumbnail --convert-thumbnails jpg \
    --output "thumbnail:$SLUG_DIR/thumb.%(ext)s" "<URL>" 2>/dev/null || true
  echo "🎬 YouTube-only — bỏ qua tải video.mp4"
fi
```

> Thumbnail không bắt buộc — app tự lấy `https://img.youtube.com/vi/$YT_ID/hqdefault.jpg` nếu thiếu.

**Nhánh tải video** (không phải YouTube-only): tải `video.mp4` + thumbnail như cũ.

```bash
if [ "$YOUTUBE_ONLY" = "0" ]; then
  if [ -s "$SLUG_DIR/video.mp4" ]; then
    echo "video.mp4 đã tồn tại — dùng lại"
  else
    yt-dlp \
      --format "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
      --merge-output-format mp4 \
      --write-thumbnail --convert-thumbnails jpg \
      --output "$SLUG_DIR/video.%(ext)s" \
      --output "thumbnail:$SLUG_DIR/thumb.%(ext)s" \
      --no-playlist "<URL>"
  fi
fi
```

## Bước 5 — Fallback: Whisper local (CHỈ khi `USE_YT_CAPTION=0`)

Bỏ qua hoàn toàn nếu `USE_YT_CAPTION=1`. Nhánh này luôn có `video.mp4` (vì không có caption →
`YOUTUBE_ONLY=0` → đã tải ở Bước 4).

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
            out.append(f\"[{s['start']:.1f}s → {s['end']:.1f}s] {s['text'].strip()}\")
print('\n'.join(out))
"
```

Đọc kỹ output (mỗi dòng có khoảng thời gian `[12.3s → 14.8s]`: lấy `start` và `end` đúng
của segment cho field `start`/`end` của câu hỏi — gộp nhiều segment liền nhau nếu đáp án trải dài).

**2. Soạn câu hỏi** — bám sát dạng đề IELTS Listening, trộn nhiều dạng cho đủ ~10 câu:

- **Multiple choice** (A/B/C) — 3–4 câu
- **Sentence / Note completion** — 3 câu, có giới hạn từ (`word_limit`) viết **bằng tiếng Việt**, vd `"KHÔNG QUÁ HAI TỪ VÀ/HOẶC MỘT CON SỐ"`. Đáp án phải là **đúng từ xuất hiện trong transcript**, và `word_limit` phải **khớp số từ thực tế của đáp án**. Lưu ý tiếng Việt đếm từ theo **âm tiết / khoảng trắng** — vd "tuyệt vọng", "bác sĩ" = **2 từ** (không phải 1).
  Các mẫu `word_limit` tiếng Việt: `"CHỈ MỘT TỪ"`, `"KHÔNG QUÁ HAI TỪ"`, `"KHÔNG QUÁ BA TỪ"`, `"MỘT CON SỐ"`, `"KHÔNG QUÁ HAI TỪ VÀ/HOẶC MỘT CON SỐ"`.
- **Short-answer** — 2 câu, đáp án ngắn lấy trực tiếp từ audio.
- **Matching / Multiple choice (gist hoặc suy luận)** — 1–2 câu.

Nguyên tắc chuẩn IELTS:
- Câu hỏi phải **trả lời được hoàn toàn từ nội dung audio** — không hỏi kiến thức ngoài.
- Dùng **paraphrase** (diễn đạt lại) trong câu hỏi thay vì lặp y nguyên câu trong transcript — đây là điểm cốt lõi IELTS.
- Sắp theo **thứ tự xuất hiện** trong video (như đề thật).
- Mỗi câu kèm `start` (giây bắt đầu) **và** `end` (giây kết thúc) của đoạn nghe được đáp án —
  lấy đúng `start`/`end` từ transcript, để app phát đúng đoạn rồi dừng. Nếu đáp án trải nhiều
  segment liền nhau thì `start` = start segment đầu, `end` = end segment cuối. Kèm `explanation`
  ngắn trích câu gốc.

**3. Ghi file** `output/<slug>/ielts_listening.json` theo schema:

```json
{
  "title": "<Tiêu đề bài viết>",
  "slug": "<slug>",
  "youtube_id": "<YT_ID khi YOUTUBE_ONLY=1, ngược lại BỎ field này>",
  "source_transcript": "youtube:json3 | faster-whisper",
  "level": "IELTS Listening",
  "total": 10,
  "created_at": "<ISO>"
  "questions": [
    {
      "no": 1,
      "type": "multiple_choice",
      "question": "What is the Coral Board mainly designed for?",
      "options": ["A. Cloud training", "B. On-device AI", "C. Web hosting"],
      "answer": "B. On-device AI",
      "word_limit": null,
      "start": 1.5,
      "end": 6.8,
      "explanation": "\"built for on-device AI ... machine learning accelerator inside\""
    },
    {
      "no": 2,
      "type": "sentence_completion",
      "question": "The board is small, low power and built for developers to ____ on embedded devices.",
      "options": [],
      "answer": "experiment",
      "word_limit": "CHỈ MỘT TỪ",
      "start": 8.0,
      "end": 12.4,
      "explanation": "\"built for developers to experiment with on embedded devices\""
    }
  ]
}
```

> `type` ∈ `multiple_choice | sentence_completion | note_completion | short_answer | matching`.
> Nếu transcript quá ngắn (< ~80 từ) thì soạn ít hơn 10 câu cũng được — báo rõ số câu thực tế.
> Ghi file bằng Write tool, không cần script riêng.
> **Quan trọng:** chỉ thêm field `"youtube_id": "$YT_ID"` khi `YOUTUBE_ONLY=1` (clip không có
> `video.mp4`, phát qua iframe). Nếu đã tải `video.mp4` thì BỎ field này để app dùng `<video>` local.

## Bước 7 — Báo kết quả

Hiển thị:

- Slug: `<slug>`
- Đường dẫn: `output/<slug>/`
- Nguồn transcript: **YouTube caption** (`source: youtube:json3`) hay **Whisper local** (`faster-whisper:*`)
- **Chế độ phát**: **YouTube iframe** (YOUTUBE_ONLY — không có `video.mp4`, có `youtube_id`)
  hay **MP4 local** (`<video>`)
- Số file transcript: N (caption = 1 file; Whisper = số part)
- Câu hỏi IELTS: đã sinh N câu → `output/<slug>/ielts_listening.json`
- Nhắc mở `all-video.html`:
  - clip **MP4 local** → mở `file://` cũng được.
  - clip **YouTube-only** → PHẢI mở qua `http://localhost...` (vd `python3 -m http.server`),
    KHÔNG mở `file://` (YouTube iframe chặn origin `null` → lỗi 153).

## Xử lý lỗi

- Nếu `yt-dlp` (tải video) thất bại: báo lỗi và dừng
- Caption YouTube không có/parse lỗi: KHÔNG phải lỗi — tự fallback Whisper local (Bước 5)
- Nếu 1 part Whisper lỗi: ghi log, tiếp tục các part còn lại, báo cáo cuối
- Nếu `ffmpeg` segment lỗi: thử tải lại hoặc dừng với thông báo rõ ràng

## Lưu ý ngôn ngữ

- **Caption YouTube** tự đúng ngôn ngữ gốc nhờ `--sub-langs ".*-orig"` (lấy bản `-orig`,
  KHÔNG lấy bản dịch máy như `vi` trên video tiếng Anh) — không cần chỉ định ngôn ngữ.
- **Whisper fallback**: mặc định `--language en`. Video tiếng Việt → đổi sang `--language vi`.
