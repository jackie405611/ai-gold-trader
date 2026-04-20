# ============================================================
#  launcher.py  —  Telegram-controlled launcher for main.py
#  รันไฟล์นี้แทน main.py เพื่อให้ควบคุมผ่าน Telegram ได้
#
#  คำสั่ง:
#    /runmain   — เริ่ม main.py
#    /stopmain  — หยุด main.py
#    /restart   — รีสตาร์ท main.py
#    /mainstat  — ดูสถานะว่า main.py รันอยู่หรือไม่
# ============================================================
import subprocess
import sys
import time
import requests

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
_last_update = 0
_proc: subprocess.Popen | None = None


def _send(text: str):
    try:
        requests.post(
            f"{_BASE}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=8,
        )
    except Exception as e:
        print(f"[Launcher] send error: {e}")


def _is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def _start():
    global _proc
    if _is_running():
        _send("⚠️ <b>main.py กำลังรันอยู่แล้ว</b>\nใช้ /restart เพื่อรีสตาร์ท")
        return
    _proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=".",
    )
    _send(f"✅ <b>main.py เริ่มทำงานแล้ว</b>\nPID: <code>{_proc.pid}</code>")
    print(f"[Launcher] Started main.py PID={_proc.pid}")


def _stop():
    global _proc
    if not _is_running():
        _send("⚠️ main.py ไม่ได้รันอยู่")
        return
    _proc.terminate()
    try:
        _proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _proc.kill()
    _send("🛑 <b>main.py หยุดทำงานแล้ว</b>")
    print(f"[Launcher] Stopped main.py PID={_proc.pid}")
    _proc = None


def _status():
    if _is_running():
        _send(f"✅ <b>main.py กำลังรันอยู่</b>\nPID: <code>{_proc.pid}</code>")
    else:
        _send("⏸ <b>main.py ไม่ได้รันอยู่</b>\nพิมพ์ /runmain เพื่อเริ่ม")


def _handle(text: str, username: str):
    cmd = text.strip().split()[0].lower()

    if cmd == "/runmain":
        _start()
    elif cmd == "/stopmain":
        _stop()
    elif cmd == "/restart":
        if _is_running():
            _stop()
            time.sleep(2)
        _start()
    elif cmd == "/mainstat":
        _status()
    else:
        _send(
            "❓ <b>Launcher Commands</b>\n\n"
            "/runmain  — เริ่ม main.py\n"
            "/stopmain — หยุด main.py\n"
            "/restart  — รีสตาร์ท main.py\n"
            "/mainstat — ดูสถานะ main.py"
        )


def _poll():
    global _last_update
    print("[Launcher] Polling Telegram...")

    while True:
        # Auto-restart หาก main.py หยุดเองโดยไม่ได้สั่ง
        if _proc is not None and _proc.poll() is not None:
            print(f"[Launcher] main.py exited (code={_proc.poll()}) — auto-restart in 10s")
            _send(f"⚠️ <b>main.py หยุดทำงานเองโดยไม่ได้สั่ง</b> (exit code={_proc.poll()})\nจะรีสตาร์ทใน 10 วินาที...")
            time.sleep(10)
            _start()

        try:
            resp = requests.get(
                f"{_BASE}/getUpdates",
                params={"offset": _last_update + 1, "timeout": 5},
                timeout=12,
            )
            if resp.status_code != 200:
                time.sleep(3)
                continue

            for upd in resp.json().get("result", []):
                _last_update = upd["update_id"]
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                if str(msg["chat"]["id"]) != str(TELEGRAM_CHAT_ID):
                    continue
                text = msg.get("text", "")
                user = msg.get("from", {}).get("username", "unknown")
                if text.startswith("/"):
                    print(f"[Launcher] @{user}: {text}")
                    _handle(text, user)

        except Exception as e:
            print(f"[Launcher] Poll error: {e}")

        time.sleep(2)


if __name__ == "__main__":
    _send("🚀 <b>Launcher พร้อมแล้ว</b>\nพิมพ์ /runmain เพื่อเริ่ม main.py")
    print("[Launcher] Ready. Send /runmain to start bot.")
    _poll()
