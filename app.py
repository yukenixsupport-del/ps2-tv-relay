import os
from flask import Flask, Response, stream_with_context
import requests

app = Flask(__name__)

RADIO_URL = "http://37.247.98.7:80/;stream.mp3"


@app.route("/")
@app.route("/radyo")
def radyo_proxy():
  def generate():
    try:
      headers = {
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          )
      }
      # Akışı bağlantıyı koparmadan parça parça (32KB) okuyoruz
      with requests.get(RADIO_URL, headers=headers, stream=True, timeout=10) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=32768):
          if chunk:
            yield chunk
    except Exception as e:
      print(f"Yayın akış hatası: {e}")

  return Response(
      stream_with_context(generate()),
      mimetype="audio/mpeg",
      headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
  )


if __name__ == "__main__":
  # Render'ın atadığı dinamik portu kullanır, lokalde 10000 portuyla çalışır
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)
