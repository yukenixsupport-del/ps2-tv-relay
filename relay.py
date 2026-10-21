import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

CONFIG_PATH = Path(os.environ.get("RELAY_CONFIG", "relay_channels.json"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8080")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
# Android ortamında sorun olmaması için varsayılan port 8080 yapıldı
LISTEN_PORT = int(os.environ.get("PORT", "8080"))


def load_channels():
    if not CONFIG_PATH.exists():
        return []
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        channels = json.load(config_file)
    if not isinstance(channels, list):
        raise ValueError("relay_channels.json bir liste olmali")
    return channels


def find_channel(slug):
    for channel in load_channels():
        if channel.get("slug") == slug and channel.get("source"):
            return channel
    return None


def public_channels():
    channels = load_channels()
    base_url = PUBLIC_BASE_URL.rstrip("/")
    return {
        "radyolar": [
            {
                "isim": channel["isim"],
                "url": f"{base_url}/radio/{channel['slug']}",
            }
            for channel in channels
            if channel.get("isim") and channel.get("slug") and channel.get("source")
        ],
        "tv_kanallari": [
            {
                "isim": channel["isim"],
                "url": f"{base_url}/tv/{channel['slug']}",
            }
            for channel in channels
            if channel.get("isim") and channel.get("slug") and channel.get("source")
        ],
    }


def ffmpeg_command(channel, mode="tv"):
    """
    mode='tv'    -> MPEG2 Video + MP2 Ses (PS2 TV Uyumlu)
    mode='radio' -> Sadece MP3 Ses (Radyo / Müzik Dinlemek İçin)
    """
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]

    if channel["source"] == "test-pattern":
        command.extend(["-re", "-f", "lavfi", "-i", "testsrc=size=352x288:rate=25"])
    else:
        command.extend([
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
        ])
        if channel.get("loop", False):
            command.extend(["-stream_loop", "-1"])
        command.extend(["-i", channel["source"]])

    if mode == "radio":
        # SADECEMENT SES (RADYO) MODU
        command.extend([
            "-vn",                  # Videoyu kapat
            "-c:a", "libmp3lame",    # MP3 Ses Formatı
            "-b:a", "128k",         # 128 kbps Ses Kalitesi
            "-f", "mp3",            # MP3 Stream
            "pipe:1"
        ])
    else:
        # VIDEO + SES MODU (PS2 UYUMU)
        command.extend([
            "-vf", "scale=352:288:force_original_aspect_ratio=decrease,pad=352:288:(ow-iw)/2:(oh-ih)/2",
            "-r", "25",
            "-c:v", "mpeg2video",
            "-pix_fmt", "yuv420p",
            "-b:v", "1200k",
            "-maxrate", "1400k",
            "-bufsize", "600k",
            "-c:a", "mp2",           # SES EKLENDİ (-an KALDIRILDI)
            "-b:a", "128k",
            "-ar", "44100",
            "-f", "mpeg2video",
            "pipe:1"
        ])

    return command


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args), flush=True)

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        
        if path in ["/", "/kanallar.json"]:
            self.send_json(public_channels())
            return
            
        if path.startswith("/radio/"):
            self.stream_channel(path[7:], mode="radio")
            return

        if path.startswith("/tv/"):
            self.stream_channel(path[4:], mode="tv")
            return

        self.send_error(404, "Not found")

    def send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def stream_channel(self, slug, mode="tv"):
        channel = find_channel(slug)
        if channel is None:
            self.send_error(404, "Unknown channel")
            return

        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_command(channel, mode=mode),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            
            content_type = "audio/mpeg" if mode == "radio" else "video/mpeg"
            
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            while True:
                data = process.stdout.read(32768)
                if not data:
                    break
                self.wfile.write(data)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), RelayHandler)
    print(f"PS2 relay listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    server.serve_forever()
