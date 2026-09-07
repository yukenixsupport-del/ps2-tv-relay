import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

CONFIG_PATH = Path(os.environ.get("RELAY_CONFIG", "relay_channels.json"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("PORT", "80"))


def load_channels():
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
    return {
        "radyolar": [],
        "tv_kanallari": [
            {
                "isim": channel["isim"],
                "url": PUBLIC_BASE_URL.rstrip("/") + "/tv/" + channel["slug"],
            }
            for channel in load_channels()
            if channel.get("isim") and channel.get("slug") and channel.get("source")
        ],
    }


def ffmpeg_command(channel):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if channel["source"] == "test-pattern":
        command.extend(["-re", "-f", "lavfi", "-i", "testsrc=size=352x288:rate=25"])
    else:
        command.extend(
            [
                "-reconnect",
                "1",
                "-reconnect_streamed",
                "1",
                "-reconnect_delay_max",
                "5",
            ]
        )
        if channel.get("loop", False):
            command.extend(["-stream_loop", "-1"])
        command.extend(["-i", channel["source"]])
    command.extend(
        [
            "-an",
            "-vf",
            "scale=352:288:force_original_aspect_ratio=decrease,pad=352:288:(ow-iw)/2:(oh-ih)/2",
            "-r",
            "25",
            "-c:v",
            "mpeg2video",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            "1200k",
            "-maxrate",
            "1400k",
            "-bufsize",
            "600k",
            "-f",
            "mpeg2video",
            "pipe:1",
        ]
    )
    return command


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args), flush=True)

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path == "/kanallar.json":
            self.send_json(public_channels())
            return
        if path.startswith("/tv/"):
            self.stream_channel(path[4:])
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

    def stream_channel(self, slug):
        channel = find_channel(slug)
        if channel is None:
            self.send_error(404, "Unknown channel")
            return

        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_command(channel),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
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
    print("PS2 relay listening on %s:%d" % (LISTEN_HOST, LISTEN_PORT), flush=True)
    server.serve_forever()
