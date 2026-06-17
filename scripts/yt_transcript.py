#!/usr/bin/env python3
"""
YouTube auto-caption (json3) → JSON SCHEMA CHUNG (giống transcribe.py) ra stdout.

Ưu tiên dùng caption gốc của YouTube để khỏi chạy Whisper local nặng. Chỉ dùng được
khi video có auto-caption `<lang>-orig`. Không có thì pipeline fallback sang transcribe.py.

Usage:
    python yt_transcript.py <file.json3>

In ra stdout DUY NHẤT 1 dòng JSON:
    {"text", "duration", "words":[{"word","start","end"}],
     "segments":[{"text","start","end"}], "source":"youtube:json3"}

Mọi log đi qua stderr để stdout sạch JSON cho Node parse.
"""
import sys
import io
import json
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Rác YouTube chèn vào auto-caption: sound-tag "[music]"/"[Applause]" và marker đổi
# người nói ">>". Bị tách rời qua nhiều seg nên phải làm sạch ở mức ký tự, không thể
# lọc theo token. Thay bằng khoảng trắng CÙNG ĐỘ DÀI để giữ nguyên ánh xạ offset.
BRACKET_RE = re.compile(r"\[[^\]]*\]")
SPEAKER_RE = re.compile(r">>")


def _blank(m):
    return " " * (m.end() - m.start())


def convert(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    words = []
    segments = []
    text_parts = []

    for ev in data.get("events", []):
        segs = ev.get("segs") or []
        t0 = ev.get("tStartMs")
        if t0 is None:
            continue
        dur = ev.get("dDurationMs", 0) or 0
        ev_end = (t0 + dur) / 1000.0

        # Ghép cả event thành 1 chuỗi + mảng offset tuyệt đối (ms) theo từng ký tự.
        chars, offs = [], []
        for s in segs:
            raw = s.get("utf8", "")
            off = t0 + (s.get("tOffsetMs", 0) or 0)
            for ch in raw:
                chars.append(ch)
                offs.append(off)
        full = "".join(chars)

        # Xoá sound-tag + marker (giữ độ dài để offs vẫn khớp index).
        full = BRACKET_RE.sub(_blank, full)
        full = SPEAKER_RE.sub(_blank, full)

        line_tokens = []
        for m in re.finditer(r"\S+", full):
            tok = m.group()
            line_tokens.append(tok)
            words.append({"word": tok,
                          "start": round(offs[m.start()] / 1000.0, 3)})

        line = " ".join(line_tokens).strip()
        if line:
            segments.append({"text": line, "start": round(t0 / 1000.0, 3),
                             "end": round(ev_end, 3)})
            text_parts.append(line)

    # YouTube auto-caption là kiểu "rolling": dDurationMs là thời gian HIỂN THỊ của
    # dòng (~4.5s), gối đầu lên 1–2 dòng kế tiếp → end của segment bị phồng, các câu
    # chồng lấn nhau ~2s. Khi all-video.html phát từng câu (currentTime: start→end),
    # audio lố sang câu sau → nghe "chậm/không khớp". Cắt gọn end về đúng start của
    # câu kế tiếp để mỗi câu khít với lời nói.
    for i in range(len(segments) - 1):
        nxt_start = segments[i + 1]["start"]
        if segments[i]["start"] < nxt_start < segments[i]["end"]:
            segments[i]["end"] = nxt_start

    # end của mỗi từ = start của từ kế tiếp; từ cuối lấy end của segment chứa nó.
    for i, w in enumerate(words):
        if i + 1 < len(words):
            w["end"] = words[i + 1]["start"]
        else:
            w["end"] = max((seg["end"] for seg in segments), default=w["start"])
        if w["end"] < w["start"]:
            w["end"] = w["start"]

    duration = max((seg["end"] for seg in segments), default=0.0)
    return {
        "text": " ".join(text_parts).strip(),
        "duration": round(duration, 3),
        "words": words,
        "segments": segments,
        "source": "youtube:json3",
    }


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python yt_transcript.py <file.json3>\n")
        sys.exit(2)
    result = convert(sys.argv[1])
    if not result["words"]:
        sys.stderr.write("⚠️  json3 không có từ nào sau khi lọc — coi như không dùng được.\n")
        sys.exit(3)
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
