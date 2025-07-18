from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from app.slack_handler import handle_slack_event
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Slack Toxicity Monitor is running!"

@app.route("/slack/events", methods=["POST"])
def slack_events():
    response = handle_slack_event(request)
    if response is None:
        return jsonify({"status": "ok"}), 200
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)