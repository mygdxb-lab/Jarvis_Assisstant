import os
import json
import requests
import anthropic
from datetime import datetime

# ── Config ──────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "mygdxb-lab/Jarvis_Assisstant"
OFFSET_FILE = "memory/telegram-offset.json"

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Anthropic Client ─────────────────────────────────────
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── GitHub Helpers ───────────────────────────────────────
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

# ── Memory Loader ────────────────────────────────────────
def load_memory():
    profile, _ = github_get("memory/my-profile.md")
    learnings, _ = github_get("memory/global-learnings.md")
    return profile or "", learnings or ""

# ── Save Learnings ───────────────────────────────────────
def save_learning(new_insight):
    content, sha = github_get("memory/global-learnings.md")
    if content and sha:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        updated = content + f"\n- [{timestamp}] {new_insight}"
        github_update(
            "memory/global-learnings.md",
            updated,
            sha,
            f"memory: Jarvis learned something new"
        )

# ── Telegram Helpers ─────────────────────────────────────
def get_updates(offset=None):
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params=params)
    return r.json().get("result", [])

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })

# ── Offset Persistence ───────────────────────────────────
def get_offset():
    content, _ = github_get(OFFSET_FILE)
    if content:
        return json.loads(content).get("offset", None)
    return None

def save_offset(offset):
    content, sha = github_get(OFFSET_FILE)
    new_content = json.dumps({"offset": offset})
    if sha:
        github_update(OFFSET_FILE, new_content, sha, "chore: update telegram offset")
    else:
        # Create file if it doesn't exist
        import base64
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{OFFSET_FILE}"
        requests.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json={
            "message": "chore: create telegram offset file",
            "content": base64.b64encode(new_content.encode()).decode()
        })

# ── Jarvis Brain ─────────────────────────────────────────
def ask_jarvis(user_message, profile, learnings):
    system_prompt = f"""You are Jarvis, a personal AI assistant and second brain for your owner.
You are not a generic assistant. You know your owner deeply and grow smarter over time.

Here is what you know about your owner:
{profile}

Here are your accumulated learnings and insights:
{learnings}

Your personality:
- Direct and concise. No fluff.
- Proactive — flag problems, suggest ideas, connect dots across projects
- You remember everything and reference past context naturally
- You adopt to your owner's style over time
- You are honest — you push back when needed
- You end responses with a learning tag if you learned something new about your owner or their work, formatted as: LEARNING: <one line insight>

Current date and time: {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC
"""
    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return response.content[0].text

# ── Main Loop ────────────────────────────────────────────
def main():
    print("Jarvis is awake...")
    profile, learnings = load_memory()
    offset = get_offset()

    updates = get_updates(offset)

    for update in updates:
        offset = update["update_id"] + 1
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not text or not chat_id:
            continue

        print(f"Message from {chat_id}: {text}")

        # Get Jarvis response
        reply = ask_jarvis(text, profile, learnings)

        # Check if Jarvis learned something
        if "LEARNING:" in reply:
            parts = reply.split("LEARNING:")
            clean_reply = parts[0].strip()
            insight = parts[1].strip()
            save_learning(insight)
        else:
            clean_reply = reply

        send_message(chat_id, clean_reply)

    save_offset(offset)
    print("Jarvis done.")

if __name__ == "__main__":
    main()
