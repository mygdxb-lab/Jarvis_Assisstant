import os
import json
import time
import requests
import anthropic
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "mygdxb-lab/Jarvis_Assisstant"
OFFSET_FILE = "memory/telegram-offset.json"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def github_get(path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    r = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
    if r.status_code == 200:
        import base64
        return base64.b64decode(r.json()["content"]).decode("utf-8"), r.json()["sha"]
    return None, None

def github_update(path, content, sha, message):
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha
    }
    requests.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json=payload)

def github_create(path, content, message):
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    requests.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json={
        "message": message,
        "content": base64.b64encode(content.encode()).decode()
    })

def load_memory():
    profile, _ = github_get("memory/my-profile.md")
    learnings, _ = github_get("memory/global-learnings.md")
    return profile or "", learnings or ""

def save_learning(new_insight):
    content, sha = github_get("memory/global-learnings.md")
    if content and sha:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        updated = content + f"\n- [{timestamp}] {new_insight}"
        github_update("memory/global-learnings.md", updated, sha, "memory: Jarvis learned something new")

def get_updates(offset=None):
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=35)
        return r.json().get("result", [])
    except:
        return []

def send_message(chat_id, text):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })
    except:
        pass

def get_offset():
    content, _ = github_get(OFFSET_FILE)
    if content:
        try:
            return json.loads(content).get("offset", None)
        except:
            return None
    return None

def save_offset(offset):
    content, sha = github_get(OFFSET_FILE)
    new_content = json.dumps({"offset": offset})
    if sha:
        github_update(OFFSET_FILE, new_content, sha, "chore: update telegram offset")
    else:
        github_create(OFFSET_FILE, new_content, "chore: create telegram offset file")

def ask_jarvis(user_message, profile, learnings):
    system_prompt = f"""You are Jarvis, a personal AI assistant and second brain.
You know your owner deeply and grow smarter over time.

Owner profile:
{profile}

Accumulated learnings:
{learnings}

Your personality:
- Direct and concise. No fluff.
- Proactive — flag problems, suggest ideas, connect dots
- You remember everything and reference past context naturally
- Honest — push back when needed
- If you learn something new about your owner, end with: LEARNING: <one line insight>

Current time: {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return response.content[0].text

def main():
    print("Jarvis is awake and listening...")
    offset = get_offset()
    profile, learnings = load_memory()
    last_memory_refresh = time.time()

    while True:
        try:
            # Refresh memory every 10 minutes
            if time.time() - last_memory_refresh > 600:
                profile, learnings = load_memory()
                last_memory_refresh = time.time()
                print("Memory refreshed.")

            updates = get_updates(offset)

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "")

                if not text or not chat_id:
                    continue

                print(f"Message: {text}")
                reply = ask_jarvis(text, profile, learnings)

                if "LEARNING:" in reply:
                    parts = reply.split("LEARNING:")
                    clean_reply = parts[0].strip()
                    insight = parts[1].strip()
                    save_learning(insight)
                else:
                    clean_reply = reply

                send_message(chat_id, clean_reply)
                save_offset(offset)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Jarvis is alive")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    main()

