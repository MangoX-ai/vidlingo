# vidlingo

🎬 Turn online videos into ready-to-study English lessons — transcribe, translate, learn.

Công cụ cá nhân giúp **tạo bài học tiếng Anh từ video trên mạng**: tự động bóc
transcript (STT bằng Whisper local) và dịch để học. Toàn bộ pipeline chạy trên máy
của bạn — xem trong `all-video.html`.

## Cài đặt

Dự án dùng [Claude Code](https://claude.com/claude-code) để tự động hoá việc setup.
Sau khi clone, **chỉ cần chạy một lệnh duy nhất**:

```
/init-project
```

Skill `init-project` sẽ tự động:

1. Kiểm tra hệ thống (Python3, `yt-dlp`, `ffmpeg`).
2. Cài các system tool còn thiếu (Homebrew trên macOS, apt/pip trên Linux, winget trên Windows).
3. Tạo Python virtualenv trong `scripts/.venv` và cài dependencies (`requirements.txt`).
4. Verify Whisper local (`faster-whisper`) — đây là STT engine chính, chạy CPU, không cần GPU/internet.
5. Tạo thư mục `output/`.
6. (Tuỳ chọn) Kiểm tra GPU API để tăng tốc — không có cũng không sao.

Khi báo `🎉 Dự án đã sẵn sàng!` là xong. Không cần cấu hình thủ công gì thêm.

## Sử dụng

Thêm video mới (tự chạy toàn bộ pipeline tải + transcript + thumbnail):

```
/lang-lesson-builder <youtube-url>
```

Mở `all-video.html` trong trình duyệt để xem và học.

## Yêu cầu hệ thống

- Python 3
- `yt-dlp`, `ffmpeg` (init-project tự cài)
- macOS / Linux / Windows

## Miễn trừ trách nhiệm

Tool này được xây dựng **chỉ cho mục đích cá nhân** — giúp người dùng tải về máy local
và dịch nội dung video nước ngoài để **hiểu và học ngoại ngữ**, xem offline.

Người dùng tự chịu trách nhiệm đảm bảo việc sử dụng tool tuân thủ điều khoản dịch vụ
(Terms of Service) của nền tảng tương ứng và pháp luật hiện hành về bản quyền. Bất kỳ
hình thức **reup, phân phối lại, đăng tải lại hoặc khai thác thương mại** nội dung tải
về — nếu vi phạm chính sách của nền tảng hoặc quyền của chủ sở hữu nội dung — đều
**không thuộc phạm vi trách nhiệm** của tác giả/bên cung cấp tool.

Tác giả không chịu trách nhiệm với bất kỳ hành vi sử dụng nào ngoài mục đích nêu trên.

## License

[Apache License 2.0](LICENSE) — Copyright 2026 MangoAds.
