import os, json, time, hmac, hashlib, urllib.parse, base64
import boto3
import urllib.request
from boto3.dynamodb.conditions import Key
import uuid
import re

# --- AWS clients ---
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

# --- ENV / Settings ---
DDB_TABLE_NAME       = os.environ["DDB_TABLE_NAME"]
SSM_SLACK_TOKEN      = os.environ["SSM_SLACK_TOKEN"]
SKIP_SIG             = os.environ.get("SKIP_SLACK_SIG", "false").lower() == "true"
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

# Human‑readable label and slash command name for messages/help
SESSION_LABEL = os.getenv("SESSION_LABEL", "staging")     # e.g. "staging", "JupyterHub"
SLASH_COMMAND = os.getenv("SLASH_COMMAND", "/staging")   # e.g. "/staging", "/jhub"

# GSI names (same as in Terraform)
DDB_GSI_DUE    = os.getenv("DDB_GSI_DUE", "gsi_due")         # PK: gsi_pk, SK: next_ping_at
DDB_GSI_EXPIRE = os.getenv("DDB_GSI_EXPIRE", "gsi_expire")   # PK: gsi_pk, SK: expires_at

# gsi_pk values
GSI_PARTITION_PING   = "PING"     # active sessions and waiting for a response during the grace period
GSI_PARTITION_EXPIRE = "EXPIRE"   # LEGACY: kept for purge()

# Business settings
DEFAULT_SESSION_HOURS      = float(os.getenv("DEFAULT_SESSION_HOURS", "1"))   # default for start without argument and for Yes
MAX_SESSION_HOURS          = float(os.getenv("MAX_SESSION_HOURS", "8"))       # hard upper bound
PING_CONFIRMATION_MINUTES  = int(os.getenv("PING_CONFIRMATION_MINUTES", "5")) # how long we wait for a reply after ping

# Where to log actions
CHANNEL_LOG_ID = os.getenv("CHANNEL_LOG_ID", "")

# Grafana Silence settings
GRAFANA_SILENCE_ENABLED = os.getenv("GRAFANA_SILENCE_ENABLED", "false").lower() == "true"
GRAFANA_API_URL         = os.getenv("GRAFANA_API_URL", "")          # e.g. https://grafana.example.com
SSM_GRAFANA_TOKEN       = os.getenv("SSM_GRAFANA_TOKEN", "")        # SSM param name for Grafana SA token
SILENCE_DDB_USER_ID     = "__SYSTEM__"
SILENCE_DDB_SESSION_ID  = "grafana_silence"

# DDB table
table = dynamodb.Table(DDB_TABLE_NAME)

# ---------------- Slack helpers ----------------
def get_slack_token():
    resp = ssm.get_parameter(Name=SSM_SLACK_TOKEN, WithDecryption=True)
    return resp["Parameter"]["Value"]

def ping_slack_user(user_id, message, max_retries=3):
    slack_token = get_slack_token()
    slack_api_url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-type": "application/json"
    }
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Yes"}, "value": user_id, "action_id": "confirm_yes"},
                {"type": "button", "text": {"type": "plain_text", "text": "No"},  "value": user_id, "action_id": "confirm_no"},
            ]
        }
    ]
    data = {"channel": user_id, "text": message, "blocks": blocks}

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(slack_api_url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req) as resp:
                response_body = resp.read()
                response_json = json.loads(response_body.decode())
                print(f"[SLACK] Attempt {attempt + 1}: Response ->", response_json)
                if response_json.get("ok"):
                    return response_json.get("channel"), response_json.get("ts")
                else:
                    print(f"[WARN] Slack returned ok=False: {response_json}")
        except Exception as e:
            print(f"[ERROR] Slack ping exception on attempt {attempt + 1}: {e}")
        time.sleep(2)

    print("[FAIL] All attempts to ping Slack user failed.")
    return None, None

def log_action_to_channel(user_id, action_type, extra_text=None):
    slack_token = get_slack_token()
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {slack_token}", "Content-type": "application/json"}
    label = SESSION_LABEL.capitalize()
    action_text = {
        "start": f"▶️ {label} started by",
        "stop":  f"🛑 {label} stopped by",
        "yes":   f"✅ {label} extended (via button) by",
        "no":    f"🛑 {label} stopped (via button) by",
        "purge": f"🗑️ {label} purged by",
    }
    base = action_text.get(action_type, "❔")
    suffix = f" {extra_text}" if extra_text else ""
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"{base} <@{user_id}>{suffix}"}}]
    data = {"channel": CHANNEL_LOG_ID, "blocks": blocks}
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req) as resp:
            resp.read()
    except Exception as e:
        print("Log to channel exception:", str(e))

def expire_slack_message(channel_id, ts, user_id):
    """We try to update the original ping to 'Session expired...'; if it fails — post a separate message."""
    slack_token = get_slack_token()
    headers = {"Authorization": f"Bearer {slack_token}", "Content-type": "application/json"}
    text = f"⏳ Session expired. I'm about to stop {SESSION_LABEL}. <@{user_id}>"
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]

    # 1) chat.update
    try:
        url_upd = "https://slack.com/api/chat.update"
        data_upd = {"channel": channel_id, "ts": ts, "text": text, "blocks": blocks}
        req = urllib.request.Request(url_upd, data=json.dumps(data_upd).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req) as resp:
            resp_json = json.loads(resp.read().decode())
            print("[SLACK] chat.update:", resp_json)
            if resp_json.get("ok"):
                return
            else:
                print("[WARN] chat.update failed, fallback to postMessage:", resp_json)
    except Exception as e:
        print("[ERROR] chat.update exception, fallback to postMessage:", str(e))

    # 2) Fallback: separate message
    try:
        url_msg = "https://slack.com/api/chat.postMessage"
        data_msg = {"channel": channel_id, "text": text, "blocks": blocks}
        req2 = urllib.request.Request(url_msg, data=json.dumps(data_msg).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req2) as resp2:
            resp2_json = json.loads(resp2.read().decode())
            print("[SLACK] postMessage fallback:", resp2_json)
    except Exception as e2:
        print("[ERROR] postMessage fallback failed:", str(e2))

def send_expired_to_channel(user_id):
    """Post an 'expired' message to the shared channel."""
    slack_token = get_slack_token()
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {slack_token}", "Content-type": "application/json"}
    text = f"⏳ Session expired. I'm about to stop {SESSION_LABEL}. <@{user_id}>"
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    data = {"channel": CHANNEL_LOG_ID, "text": text, "blocks": blocks}
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req) as resp:
            resp.read()
    except Exception as e:
        print("Send expired to channel exception:", str(e))

# ---------------- Time helpers ----------------
def format_duration_human(hours_float: float) -> str:
    """Friendly text: '3 hours', '1 hour 30 min', '30 min'."""
    total_minutes = int(round(hours_float * 60))
    h, m = divmod(total_minutes, 60)
    parts = []
    if h > 0:
        parts.append(f"{h} hour" + ("" if h == 1 else "s"))
    if m > 0:
        parts.append(f"{m} min")
    return " ".join(parts) if parts else "0 min"

def parse_hours_from_token(token: str) -> float:
    """
    NEW STRICT PARSING:
    - Accept ONLY 'HH:MM' or 'H:MM' (colon separated).
      Examples: '2:00', '2:30', '0:45', '10:05'.
    - Formats with a dot (2.30, 1.5) are NOT accepted.
    - Returns duration in hours (float).
    """
    token = token.strip()

    # Allow 1–3 digits for hours (just in case), strictly two digits for minutes.
    m = re.fullmatch(r"^(\d{1,3}):([0-5]\d)$", token)
    if not m:
        raise ValueError("bad time format")
    h = int(m.group(1))
    mm = int(m.group(2))
    # No need to guard against negatives — the regex excludes them.
    hours = h + mm / 60.0
    return hours

# ---------------- Grafana Silence helpers ----------------
def get_grafana_token():
    if not SSM_GRAFANA_TOKEN:
        return None
    try:
        resp = ssm.get_parameter(Name=SSM_GRAFANA_TOKEN, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception as e:
        print(f"[ERROR] Failed to get Grafana token from SSM: {e}")
        return None

def has_active_sessions():
    """Check if there are any active sessions (gsi_pk=PING) in DDB."""
    try:
        resp = table.query(
            IndexName=DDB_GSI_DUE,
            KeyConditionExpression=Key('gsi_pk').eq(GSI_PARTITION_PING),
            Select='COUNT',
            Limit=1
        )
        count = resp.get('Count', 0)
        print(f"[SILENCE] Active session count: {count}")
        return count > 0
    except Exception as e:
        print(f"[ERROR] Failed to check active sessions: {e}")
        return True  # assume active to avoid false silence

def get_stored_silence_id():
    """Get stored Grafana silence ID from DDB."""
    try:
        resp = table.get_item(
            Key={"user_id": SILENCE_DDB_USER_ID, "session_id": SILENCE_DDB_SESSION_ID}
        )
        item = resp.get("Item")
        return item.get("silence_id") if item else None
    except Exception as e:
        print(f"[ERROR] Failed to get stored silence ID: {e}")
        return None

def store_silence_id(silence_id):
    """Store Grafana silence ID in DDB."""
    try:
        table.put_item(Item={
            "user_id": SILENCE_DDB_USER_ID,
            "session_id": SILENCE_DDB_SESSION_ID,
            "silence_id": silence_id,
            "created_at": int(time.time())
        })
    except Exception as e:
        print(f"[ERROR] Failed to store silence ID: {e}")

def delete_stored_silence_id():
    """Remove stored Grafana silence ID from DDB."""
    try:
        table.delete_item(
            Key={"user_id": SILENCE_DDB_USER_ID, "session_id": SILENCE_DDB_SESSION_ID}
        )
    except Exception as e:
        print(f"[ERROR] Failed to delete stored silence ID: {e}")

def create_grafana_silence():
    """Create a Grafana silence for all alerts when staging is scaled to zero."""
    if not GRAFANA_SILENCE_ENABLED:
        return

    existing = get_stored_silence_id()
    if existing:
        print(f"[SILENCE] Silence already exists: {existing}")
        return

    token = get_grafana_token()
    if not token:
        print("[WARN] No Grafana token configured, skipping silence creation")
        return

    url = f"{GRAFANA_API_URL}/api/alertmanager/grafana/api/v2/silences"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 365 * 86400))

    payload = {
        "matchers": [
            {"name": "alertname", "value": ".+", "isRegex": True, "isEqual": True}
        ],
        "startsAt": now,
        "endsAt": expires,
        "createdBy": "scale-to-zero-lambda",
        "comment": f"Auto-silence: {SESSION_LABEL} scaled to zero"
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            resp_body = json.loads(resp.read().decode())
            silence_id = resp_body.get("silenceID")
            print(f"[SILENCE] Created Grafana silence: {silence_id}")
            if silence_id:
                store_silence_id(silence_id)
    except Exception as e:
        print(f"[ERROR] Failed to create Grafana silence: {e}")

def delete_grafana_silence():
    """Delete the stored Grafana silence when staging scales up."""
    if not GRAFANA_SILENCE_ENABLED:
        return

    silence_id = get_stored_silence_id()
    if not silence_id:
        print("[SILENCE] No active silence to delete")
        return

    token = get_grafana_token()
    if not token:
        print("[WARN] No Grafana token configured, skipping silence deletion")
        return

    url = f"{GRAFANA_API_URL}/api/alertmanager/grafana/api/v2/silence/{silence_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        with urllib.request.urlopen(req) as resp:
            resp.read()
            print(f"[SILENCE] Deleted Grafana silence: {silence_id}")
    except Exception as e:
        print(f"[ERROR] Failed to delete Grafana silence: {e}")

    delete_stored_silence_id()

def maybe_create_silence_if_empty():
    """Create Grafana silence if no active sessions remain (staging scaling to zero)."""
    if not GRAFANA_SILENCE_ENABLED:
        return
    if not has_active_sessions():
        print("[SILENCE] No active sessions remaining, creating Grafana silence")
        create_grafana_silence()

# --------------- DDB helpers ---------------
def delete_session(user_id, session_id):
    try:
        table.delete_item(
            Key={"user_id": user_id, "session_id": session_id},
            ConditionExpression="attribute_exists(user_id) AND attribute_exists(session_id)"
        )
        print(f"[OK] Deleted session {session_id} for user {user_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to delete session {session_id} for {user_id}: {e}")
        return False

def delete_all_sessions_for_user(user_id, except_session_id=None):
    try:
        resp = table.query(
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id}
        )
        items = resp.get("Items", [])
        count = 0
        with table.batch_writer() as batch:
            for it in items:
                if except_session_id and it["session_id"] == except_session_id:
                    continue
                batch.delete_item(Key={"user_id": it["user_id"], "session_id": it["session_id"]})
                count += 1
        print(f"[OK] Deleted {count} sessions for {user_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to delete sessions for {user_id}: {e}")
        return False

def get_active_session(user_id):
    try:
        resp = table.query(
            KeyConditionExpression="user_id = :uid",
            FilterExpression="#s = :active",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":uid": user_id, ":active": "active"}
        )
        items = resp.get("Items", [])
        return items[0] if items else None
    except Exception as e:
        print(f"[ERROR] Failed to get active session for {user_id}: {e}")
        return None

def create_session(user_id, idempotency_token=None, requested_hours=None, note_for_logs=None):
    """
    Creates a new session with a configurable duration.
    next_ping_at = now + duration  (ping at the end of the session)
    expires_at   = now + duration  (TTL and anchor for gsi_expire until the ping is sent)
    """
    now = int(time.time())
    existing_session = get_active_session(user_id)
    if existing_session and (now - existing_session.get("started_at", 0) < 5):
        print(f"[SKIP] Session recently created for {user_id}, returning existing")
        return existing_session["session_id"]

    # Duration calculation
    if requested_hours is None or requested_hours <= 0:
        effective_hours = DEFAULT_SESSION_HOURS
    else:
        effective_hours = min(requested_hours, MAX_SESSION_HOURS)

    duration_sec = int(round(effective_hours * 3600))

    session_id = (
        hashlib.sha256(f"{user_id}:{idempotency_token}".encode()).hexdigest()[:16]
        if idempotency_token else str(uuid.uuid4())
    )

    # delete previous sessions of the user
    delete_all_sessions_for_user(user_id)

    item = {
        "user_id": user_id,
        "session_id": session_id,
        "status": "active",
        "started_at": now,
        "last_activity": now,

        # schedule ping at the end of the session
        "gsi_pk": GSI_PARTITION_PING,
        "next_ping_at": now + duration_sec,

        # TTL/anchor before the ping
        "expires_at": now + duration_sec,

        "ping_sent": False,
        "ping_ts": None,
        "channel_id": None,
        "message_ts": None,
        "last_button_ts": None,

        # for status/diagnostics
        "session_seconds": duration_sec,
    }

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(session_id)"
        )
        print(f"[OK] Created session {session_id} for user {user_id} for {effective_hours} hours")
        delete_grafana_silence()  # staging is coming up — remove silence
        return session_id
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"[DUPLICATE] Session {session_id} already exists for {user_id}")
        return session_id

def update_session_ping_mark_wait(user_id, session_id, channel_id, message_ts):
    """
    After sending a ping, switch the record to the “waiting for reply” mode,
    BUT keep gsi_pk=PING so the scaler doesn't turn the pod off.
    We just move expires_at to the end of the grace window and set ping_sent=True.
    """
    now = int(time.time())
    confirm_at = now + (PING_CONFIRMATION_MINUTES * 60)
    try:
        table.update_item(
            Key={"user_id": user_id, "session_id": session_id},
            UpdateExpression="""
              SET ping_sent  = :true,
                  ping_ts    = :now,
                  channel_id = :channel,
                  message_ts = :ts,
                  expires_at = :confirm_at
            """,
            ConditionExpression="(attribute_not_exists(ping_sent) OR ping_sent = :false) AND gsi_pk = :ping",
            ExpressionAttributeValues={
                ":true": True,
                ":false": False,
                ":now": now,
                ":channel": channel_id,
                ":ts": message_ts,
                ":confirm_at": confirm_at,
                ":ping": GSI_PARTITION_PING
            }
        )
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update session ping for {user_id}: {e}")
        return False

def extend_session_with_button_ts(user_id, button_ts):
    """Extension via 'Yes' button (always for the default 1 hour) and record the ts."""
    session = get_active_session(user_id)
    if not session:
        return None

    now = int(time.time())
    extend_sec = int(round(DEFAULT_SESSION_HOURS * 3600))
    try:
        table.update_item(
            Key={"user_id": user_id, "session_id": session["session_id"]},
            UpdateExpression="""
              SET last_activity   = :now,
                  next_ping_at    = :next_ping,
                  ping_sent       = :false,
                  ping_ts         = :nullv,
                  last_button_ts  = :button_ts,
                  gsi_pk          = :ping,
                  expires_at      = :ttl_extend,
                  session_seconds = :ttl_extend_sec
            """,
            ExpressionAttributeValues={
                ":now": now,
                ":next_ping": now + extend_sec,
                ":false": False,
                ":nullv": None,
                ":button_ts": button_ts,
                ":ping": GSI_PARTITION_PING,
                ":ttl_extend": now + extend_sec,
                ":ttl_extend_sec": extend_sec
            }
        )
        print(f"[OK] Extended session for user {user_id} with button_ts {button_ts} by {DEFAULT_SESSION_HOURS}h")
        return session["session_id"]
    except Exception as e:
        print(f"[ERROR] Failed to extend session for {user_id}: {e}")
        return None

# ---------------- Slack interactive ----------------
def is_slack_interactive_event(body_raw, headers):
    return (
        "content-type" in headers and
        headers["content-type"].startswith("application/x-www-form-urlencoded") and
        "payload=" in (body_raw or "")
    )

def handle_slack_interactive(body_raw):
    print("!!! handle_slack_interactive CALLED !!!")
    payload_str = urllib.parse.parse_qs(body_raw).get("payload", ["{}"])[0]
    payload = json.loads(payload_str)
    print("Slack interactive payload (parsed):", json.dumps(payload))

    action = payload.get("actions", [{}])[0]
    action_id = action.get("action_id")
    user_id = payload["user"]["id"]
    message_ts = payload.get("message", {}).get("ts", "")

    if action_id == "confirm_yes":
        session = get_active_session(user_id)
        if session:
            if session.get("last_button_ts") == message_ts:
                print(f"[DUPLICATE] Button already processed for {user_id}")
                acknowledge_interactive_action(payload["response_url"], f"✅ Session already extended")
                return _resp(200, "Already processed")
            extend_session_with_button_ts(user_id, message_ts)
        else:
            # If there is no record — create a new one for the default hour
            create_session(user_id, idempotency_token=message_ts, requested_hours=DEFAULT_SESSION_HOURS)

        acknowledge_interactive_action(payload["response_url"], f"✅ Staging extended by <@{user_id}> for {format_duration_human(DEFAULT_SESSION_HOURS)}")
        log_action_to_channel(user_id, "yes", f"for {format_duration_human(DEFAULT_SESSION_HOURS)}")
        return _resp(200, f"✅ Staging extended by <@{user_id}> for {format_duration_human(DEFAULT_SESSION_HOURS)}")

    elif action_id == "confirm_no":
        delete_all_sessions_for_user(user_id)  # hard delete
        maybe_create_silence_if_empty()  # silence alerts if staging is scaling to zero
        acknowledge_interactive_action(payload["response_url"], f"🛑 Staging stopped by <@{user_id}>")
        log_action_to_channel(user_id, "no")
        return _resp(200, f"🛑 Staging stopped by <@{user_id}>")

    return _resp(200, "Unknown action")

def acknowledge_interactive_action(response_url, text):
    data = json.dumps({"text": text, "replace_original": True}).encode("utf-8")
    req = urllib.request.Request(response_url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
    except Exception as e:
        print("Acknowledge Slack exception:", str(e))

# ---------------- Periodic jobs ----------------
def purge_all_sessions():
    """UNCHANGED: left as requested."""
    try:
        items = []
        resp1 = table.query(
            IndexName=DDB_GSI_DUE,
            KeyConditionExpression=Key('gsi_pk').eq(GSI_PARTITION_PING) & Key('next_ping_at').gte(0)
        )
        items.extend(resp1.get('Items', []))
        resp2 = table.query(
            IndexName=DDB_GSI_EXPIRE,
            KeyConditionExpression=Key('gsi_pk').eq(GSI_PARTITION_EXPIRE) & Key('expires_at').gte(0)
        )
        items.extend(resp2.get('Items', []))
        seen = set()
        deleted = 0
        with table.batch_writer() as batch:
            for it in items:
                key = (it['user_id'], it['session_id'])
                if key in seen:
                    continue
                seen.add(key)
                batch.delete_item(Key={"user_id": it["user_id"], "session_id": it["session_id"]})
                deleted += 1
        print(f"[OK] Purged {deleted} sessions")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to purge sessions: {e}")
        return False

def check_and_ping_inactive_users():
    """
    Find records with next_ping_at <= now (end of the user session),
    send ONE DM and switch the record to the waiting mode (keeping gsi_pk=PING).
    """
    now = int(time.time())
    try:
        resp = table.query(
            IndexName=DDB_GSI_DUE,
            KeyConditionExpression=Key('gsi_pk').eq(GSI_PARTITION_PING) & Key('next_ping_at').lte(now),
            ProjectionExpression='user_id, session_id, ping_sent, channel_id, message_ts'
        )
        for item in resp.get("Items", []):
            user_id    = item["user_id"]
            session_id = item["session_id"]
            ping_sent  = item.get("ping_sent", False)

            if not ping_sent:
                print(f"[INFO] Sending ping to user {user_id}")
                channel, ts = ping_slack_user(
                    user_id,
                    f":wave: <@{user_id}>, are you still working? Please answer with the button below."
                )
                if channel and ts:
                    ok = update_session_ping_mark_wait(user_id, session_id, channel, ts)
                    if not ok:
                        print(f"[WARN] Race while marking wait state for {user_id}")
                else:
                    print(f"[ERROR] Failed to ping user {user_id}")
    except Exception as e:
        print(f"[ERROR] Failed to check inactive users: {e}")

def expire_unanswered():
    """
    Those who didn't reply within the confirmation window:
      - update original DM to "Session expired..."
      - post to the service channel
      - delete the record (only if it's in PING and ping_sent=True — race guard)
    """
    now = int(time.time())
    try:
        resp = table.query(
            IndexName=DDB_GSI_EXPIRE,
            KeyConditionExpression=Key('gsi_pk').eq(GSI_PARTITION_PING) & Key('expires_at').lte(now),
            ProjectionExpression='user_id, session_id, channel_id, message_ts, ping_sent'
        )
        for it in resp.get('Items', []):
            if not it.get('ping_sent', False):
                # wasn't pinged (e.g., default session ended and immediately got extended) — skip
                continue

            uid, sid = it['user_id'], it['session_id']
            ch, ts   = it.get('channel_id'), it.get('message_ts')

            if ch and ts:
                expire_slack_message(ch, ts, uid)
            send_expired_to_channel(uid)

            try:
                table.delete_item(
                    Key={"user_id": uid, "session_id": sid},
                    ConditionExpression="gsi_pk = :ping AND ping_sent = :true",
                    ExpressionAttributeValues={":ping": GSI_PARTITION_PING, ":true": True},
                )
                print(f"[OK] Deleted session {sid} for user {uid}")
            except Exception as de:
                print(f"[ERROR] Conditional delete failed for {uid}/{sid}: {de}")
    except Exception as e:
        print(f"[ERROR] expire_unanswered failed: {e}")

    maybe_create_silence_if_empty()  # silence alerts if staging is scaling to zero

# ---------------- Slack verify ----------------
def verify_slack(body_raw, headers):
    sig = headers.get("x-slack-signature")
    timestamp = headers.get("x-slack-request-timestamp")
    if not sig or not timestamp:
        return False
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False
    sig_basestring = f"v0:{timestamp}:{body_raw}"
    my_sig = "v0=" + hmac.new(SLACK_SIGNING_SECRET.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(my_sig, sig)

def _resp(code, msg):
    return {"statusCode": code, "body": json.dumps({"text": msg}), "headers": {"Content-Type": "application/json"}}

# ---------------- Handler ----------------
def lambda_handler(event, context):
    print("=== Lambda Start ===")
    print("EVENT:", json.dumps(event))
    print("DDB_TABLE_NAME:", DDB_TABLE_NAME)

    body_raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    # Slack interactive (buttons)
    if is_slack_interactive_event(body_raw, headers):
        print("Detected Slack interactive event!")
        return handle_slack_interactive(body_raw)

    # EventBridge cron
    if event.get("source") == "aws.events":
        print(f"Detected scheduled run from EventBridge. GSIs: due={DDB_GSI_DUE} expire={DDB_GSI_EXPIRE}")
        check_and_ping_inactive_users()
        expire_unanswered()
        return _resp(200, "Scheduled ping check done")

    # Verify Slack signature (if not skipped)
    if not SKIP_SIG:
        if not verify_slack(body_raw, headers):
            print("Invalid Slack signature!")
            return _resp(401, "invalid signature")

    # Parse slash command
    cmd = None
    username = None
    try:
        payload = json.loads(body_raw)
        cmd = payload.get("text", "")
        username = payload.get("user_id")
    except Exception:
        f = urllib.parse.parse_qs(body_raw)
        cmd = f.get("text", [""])[0]
        username = f.get("user_id", [""])[0]

    print(f"Command: '{cmd}', Username: '{username}'")
    if not username:
        print("Missing username")
        return _resp(400, "need username")

    # Idempotency based on Slack timestamp
    cmd_lower = (cmd or "").lower().strip()
    request_timestamp = headers.get("x-slack-request-timestamp", str(int(time.time())))
    idempotency_token = f"{username}:{request_timestamp}:{cmd_lower}"

    # Parse command tokens: support 'start <HH:MM>'
    tokens = cmd_lower.split()
    verb = tokens[0] if tokens else "start"   # empty string — treated as 'start'
    duration_hours = None
    duration_label = None
    if verb == "start" and len(tokens) >= 2:
        try:
            raw_hours = parse_hours_from_token(tokens[1])  # now ONLY HH:MM
            clamped = min(raw_hours, MAX_SESSION_HOURS)
            duration_hours = DEFAULT_SESSION_HOURS if raw_hours <= 0 else clamped
            duration_label = format_duration_human(duration_hours)
        except Exception:
            return _resp(
                400,
                f"Bad duration format. Use: `{SLASH_COMMAND} start HH:MM` (e.g. `2:00`, `2:30`, `0:45`)."
            )

    # PURGE
    if cmd_lower == "purge":
        ok = purge_all_sessions()
        if ok:
            maybe_create_silence_if_empty()
        log_action_to_channel(username, "purge")
        return _resp(200, "All active sessions purged" if ok else "Purge failed")

    # START (and aliases)
    if verb in ("start",) or cmd_lower in ("scale", "scale normal", ""):
        req_hours = duration_hours if duration_hours is not None else DEFAULT_SESSION_HOURS
        session_id = create_session(username, idempotency_token=idempotency_token, requested_hours=req_hours)

        label = duration_label if duration_label else format_duration_human(req_hours)
        log_action_to_channel(username, "start", f"for {label}")
        return _resp(200, f"Command `{cmd}` processed for <@{username}>")

    # STOP -> delete all user's records
    if cmd_lower in ("stop", "scale0", "scale 0", "zero"):
        delete_all_sessions_for_user(username)
        maybe_create_silence_if_empty()  # silence alerts if staging is scaling to zero
        log_action_to_channel(username, "stop")
        return _resp(200, f"Command `{cmd}` processed for <@{username}>")

    # STATUS
    if cmd_lower == "status":
        session = get_active_session(username)
        if session:
            now = int(time.time())
            end_ts = int(session.get("expires_at", now))
            left_min = max(0, (end_ts - now) // 60)
            label = format_duration_human(left_min/60.0)
            return _resp(200, f"✅ Your staging session is active. Time left: {label}")
        else:
            return _resp(200, "❌ You don't have an active staging session")

    return _resp(400, "Unknown command. Use: `start [HH:MM]`, `stop`, `status`, or `purge`")
