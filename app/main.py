from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, request, jsonify
from app.slack_handler import handle_slack_event

app = Flask(__name__)

@app.route("/")
def home():
    return "Slack Toxicity Monitor is running!"

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.get_json()

    print("📨 Slack Event Received:")
    print(data)

    # Respond to URL verification challenge
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    # Pass the event to the handler
    handle_slack_event(data)

    # Respond with 200 OK for events
    return "", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)