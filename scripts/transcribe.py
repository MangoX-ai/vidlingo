#!/usr/bin/env python3
"""
faster-whisper STT — word-level timestamps → JSON SCHEMA CHUNG ra stdout.

Dùng chung cho cả 3 provider (omnivoice/vbee/elevenlabs): apply_stt_timing chỉ
cần word-timeline, nên 1 model local thay được hết.

Usage:
    python transcribe.py <audio_path> [--language vi] [--model small]
                         [--device cpu] [--compute int8]

In ra stdout DUY NHẤT 1 dòng JSON:
    {"text", "duration", "words":[{"word","start","end"}],
     "segments":[{"text","start","end"}]}

Mọi log/diagnostic đi qua stderr để stdout sạch JSON cho Node parse.

AUTO-SPLIT: Nếu audio dài hơn SPLIT_THRESHOLD_SEC (mặc định 600s = 10 phút),
tự động cắt thành các part SPLIT_PART_SEC (mặc định 300s = 5 phút) rồi ghép
kết quả lại — timestamps được offset theo từng part.
"""
import sys
import io
import json
import argparse
import os
import subprocess
import tempfile

# Windows mặc định cp1252 → ép UTF-8 để tiếng Việt có dấu không hỏng.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

SPLIT_THRESHOLD_SEC = 600   # > 10 phút thì split
SPLIT_PART_SEC      = 300   # mỗi part 5 phút


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_duration_ffprobe(path: str) -> float:
    """Lấy duration (giây) bằng ffprobe. Trả về 0.0 nếu lỗi."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", path,
            ],
            stderr=subprocess.DEVNULL,
        )
        info = json.loads(out)
        return float(info.get("format", {}).get("duration", 0.0))
    except Exception as e:
        log(f"[ffprobe] không đọc được duration: {e}")
        return 0.0


def split_audio_ffmpeg(path: str, part_sec: int, tmp_dir: str) -> list[tuple[str, float]]:
    """
    Cắt file audio thành các đoạn part_sec giây bằng ffmpeg -ss/-t.
    Trả về list[(part_path, offset_sec)] theo thứ tự.
    """
    duration = get_duration_ffprobe(path)
    parts = []
    start = 0.0
    idx = 0
    while start < duration:
        out_path = os.path.join(tmp_dir, f"part_{idx:03d}.wav")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(part_sec),
            "-i", path,
            "-ar", "16000",   # Whisper thích 16kHz
            "-ac", "1",
            out_path,
        ]
        log(f"[split] part {idx}: {start:.1f}s → {start + part_sec:.1f}s → {out_path}")
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            log(f"[split] ffmpeg lỗi part {idx}: {result.stderr.decode(errors='replace')}")
            break
        parts.append((out_path, start))
        start += part_sec
        idx += 1
    return parts


def transcribe_file(model, path: str, lang, offset: float = 0.0) -> dict:
    """
    Chạy faster-whisper trên 1 file, trả về dict chuẩn với timestamps đã offset.
    """
    log(f"[faster-whisper] transcribe {path} (offset={offset:.1f}s)")
    segments, info = model.transcribe(
        path,
        language=lang,
        word_timestamps=True,
        vad_filter=False,
    )

    words = []
    segs = []
    text_parts = []
    for seg in segments:
        seg_text = (seg.text or "").strip()
        if seg_text:
            text_parts.append(seg_text)
            segs.append({
                "text": seg_text,
                "start": round(float(seg.start) + offset, 3),
                "end":   round(float(seg.end)   + offset, 3),
            })
        for w in (seg.words or []):
            tok = (w.word or "").strip()
            if not tok:
                continue
            words.append({
                "word":  tok,
                "start": round(float(w.start) + offset, 3),
                "end":   round(float(w.end)   + offset, 3),
            })

    return {
        "text":     " ".join(text_parts).strip(),
        "duration": round(float(getattr(info, "duration", 0.0) or 0.0), 3),
        "words":    words,
        "segments": segs,
    }


def merge_results(parts: list[dict], total_duration: float, source: str) -> dict:
    """Ghép nhiều kết quả part thành 1 output cuối."""
    all_words = []
    all_segs  = []
    all_text  = []
    for p in parts:
        all_words.extend(p["words"])
        all_segs.extend(p["segments"])
        if p["text"]:
            all_text.append(p["text"])
    return {
        "text":     " ".join(all_text).strip(),
        "duration": round(total_duration, 3),
        "words":    all_words,
        "segments": all_segs,
        "source":   source,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--language", default="vi")
    ap.add_argument("--model",   default="large-v3-turbo")
    ap.add_argument("--device",  default="auto")    # auto|cpu|cuda
    ap.add_argument("--compute", default="auto")    # auto|int8|float16|float32|int8_float32
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log("[faster-whisper] thiếu thư viện. Cài: .venv/pip install -r requirements.txt")
        sys.exit(3)

    def cuda_count():
        try:
            import ctranslate2
            return ctranslate2.get_cuda_device_count()
        except Exception:
            return 0

    device = args.device
    if device == "auto":
        device = "cuda" if cuda_count() > 0 else "cpu"

    compute = args.compute
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    lang = None if args.language in ("", "auto") else args.language

    def load(dev, comp):
        log(f"[faster-whisper] load model={args.model} device={dev} compute={comp}")
        return WhisperModel(args.model, device=dev, compute_type=comp)

    try:
        model = load(device, compute)
    except Exception as e:
        if device == "cuda":
            log(f"[faster-whisper] CUDA lỗi ({e}); fallback CPU int8.")
            device, compute = "cpu", "int8"
            model = load(device, compute)
        else:
            raise

    source = f"faster-whisper:{args.model}"

    # ------------------------------------------------------------------
    # Kiểm tra duration → quyết định có split không
    # ------------------------------------------------------------------
    total_duration = get_duration_ffprobe(args.audio)
    log(f"[faster-whisper] audio duration: {total_duration:.1f}s")

    if total_duration > SPLIT_THRESHOLD_SEC:
        log(
            f"[faster-whisper] audio > {SPLIT_THRESHOLD_SEC}s → "
            f"tự động cắt thành part {SPLIT_PART_SEC}s"
        )
        with tempfile.TemporaryDirectory(prefix="whisper_split_") as tmp_dir:
            parts_info = split_audio_ffmpeg(args.audio, SPLIT_PART_SEC, tmp_dir)
            if not parts_info:
                log("[faster-whisper] split thất bại — thử transcribe nguyên file.")
                result_parts = [transcribe_file(model, args.audio, lang, offset=0.0)]
            else:
                log(f"[faster-whisper] tổng {len(parts_info)} part, bắt đầu transcribe từng part…")
                result_parts = []
                for part_path, offset in parts_info:
                    part_result = transcribe_file(model, part_path, lang, offset=offset)
                    log(
                        f"[faster-whisper] part offset={offset:.1f}s: "
                        f"{len(part_result['words'])} từ, {len(part_result['segments'])} câu"
                    )
                    result_parts.append(part_result)

        result = merge_results(result_parts, total_duration, source)
    else:
        # Audio ngắn → transcribe thẳng như cũ
        r = transcribe_file(model, args.audio, lang, offset=0.0)
        result = {**r, "source": source}
        # Ưu tiên duration từ ffprobe nếu faster-whisper trả về 0
        if result["duration"] == 0.0 and total_duration > 0:
            result["duration"] = round(total_duration, 3)

    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    log(
        f"[faster-whisper] xong: {len(result['words'])} từ word-level, "
        f"{len(result['segments'])} câu, {result['duration']}s"
    )


if __name__ == "__main__":
    main()