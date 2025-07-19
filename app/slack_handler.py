# Ensure this function is available for import in main.py
__all__ = ["handle_slack_event"]
# --- Standard Library ---
import os
import re
import time
from datetime import datetime
from threading import Thread

# --- Third-Party Libraries ---
from slack_sdk import WebClient
from slack_sdk.webhook import WebhookClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from flask import request, jsonify, abort, Response, make_response
from openai import OpenAI
from sentence_transformers import SentenceTransformer, util

# --- Toxicity Thresholds ---
AGGRESSION_THRESHOLD = 0.5
HARASSMENT_THRESHOLD = 0.5
THREAT_THRESHOLD = 0.5
COERCIVE_AUTHORITY_THRESHOLD = 0.5
CONDESCENSION_THRESHOLD = 0.3
SEXUAL_LANGUAGE_THRESHOLD = 0.5  # use harassment as proxy for sexual language if needed

# --- GPT System Prompt ---
GPT_SYSTEM_PROMPT = (
    "You are a toxicity classifier for workplace chat messages. Given the conversation context below, "
    "return a JSON object with a `scores` dictionary (toxic category: float between 0 and 1) and `triggered` list of triggered labels. "
    "Toxicity categories include: `aggression`, `harassment`, `threat`, `coercive_authority`, and `condescension`. "
    "The category `coercive_authority` refers to subtle or indirect language that pressures, monitors, or corrects someone’s behavior by "
    "implying hierarchical control, using policy speak, surveillance language, or piling on questions that make the recipient feel micromanaged or distrusted. "
    "However, if the message is from a manager responding to previous unprofessional behavior, and the tone is proportionate and necessary for accountability or clarity, it should not be flagged."
)

client = OpenAI()

openai_api_key = os.environ["OPENAI_API_KEY"]

slack_token = os.environ["SLACK_BOT_TOKEN"]
slack_signing_secret = os.environ["SLACK_SIGNING_SECRET"]

client_slack = WebClient(token=slack_token)
signature_verifier = SignatureVerifier(signing_secret=slack_signing_secret)

toxicity_log = {}

# --- Legal justification keywords (for skipping warnings if message asserts legal rights) ---
LEGAL_JUSTIFICATION_KEYWORDS = [
    "attorney general",
    "massachusetts law",
    "direito trabalhista",
    "direitos trabalhistas",
    "direito à privacidade",
    "right to privacy",
    "fair labor division",
    "consentimento",
    "consentimento expresso",
    "formal complaint",
    "complaint with the attorney general",
    "complaint with attorney general",
    "complaint with fair labor division",
    "file a complaint",
    "file a formal complaint",
    "direito de recusar",
    "não consinto",
    "não dou consentimento",
    "i do not consent",
    "i have not consented",
    "i never signed",
    "i never agreed",
    "right to keep personal property free from monitoring",
    "direito de manter propriedade pessoal livre de monitoramento",
]

def contains_legal_justification(text: str) -> bool:
    """
    Checks if the text contains legal justification keywords to skip toxicity warnings.
    """
    try:
        text_lower = text.lower()
        result = any(re.search(rf"\b{re.escape(phrase)}\b", text_lower) for phrase in LEGAL_JUSTIFICATION_KEYWORDS)
        print(f"contains_legal_justification evaluated to {result} for text: {text}")
        return result
    except Exception as e:
        print(f"Error in contains_legal_justification: {e}")
        return False

# Load model once globally
if "sbert_model" not in globals():
    sbert_model = SentenceTransformer("paraphrase-MiniLM-L6-v2")

def is_likely_quoted(text, context_window):
    """
    Returns True if the text is likely quoting any recent message from the context window.
    """
    try:
        if not context_window or not text:
            print("is_likely_quoted: No context or text provided.")
            return False

        # Extract the last few messages (assume last 5 for performance)
        recent_texts = [msg["text"] for msg in context_window[-5:] if "text" in msg and msg["text"].strip()]
        if not recent_texts:
            print("is_likely_quoted: No recent texts found in context.")
            return False

        embeddings1 = sbert_model.encode([text], convert_to_tensor=True)
        embeddings2 = sbert_model.encode(recent_texts, convert_to_tensor=True)
        cosine_scores = util.pytorch_cos_sim(embeddings1, embeddings2)

        max_score = cosine_scores.max().item()
        print(f"is_likely_quoted: max cosine similarity score = {max_score}")
        # If the message is quoting one of the previous ones (high similarity), skip
        return max_score >= 0.9
    except Exception as e:
        print(f"Error in quote similarity check: {e}")
        return False

# --- New inappropriate language check ---
def is_inappropriate_language(text):
    """
    Detects if the text contains abusive or threatening keywords.
    """
    try:
        abusive_keywords = [
            "idiota", "burro", "imbecil", "estúpido", "palhaço", "otário",
            "babaca", "retardado", "ignorante", "nojento", "vergonha", "ridículo"
        ]
        threat_keywords = [
            "vou te demitir", "você está demitido", "te mandar embora",
            "vai ser demitido", "te tirar da empresa", "vou acabar com você",
            "isso vai ter consequências", "isso não vai ficar assim"
        ]
        lowered_text = text.lower()
        for keyword in abusive_keywords + threat_keywords:
            if keyword in lowered_text:
                print(f"is_inappropriate_language: Detected keyword '{keyword}' in text.")
                return True
        print("is_inappropriate_language: No abusive keywords detected.")
        return False
    except Exception as e:
        print(f"Error in is_inappropriate_language: {e}")
        return False

def send_warning_to_slack(channel_id, message):
    """
    Sends a warning message to the specified Slack channel.
    """
    try:
        print(f"Sending warning to Slack channel {channel_id}: {message}")
        client_slack.chat_postMessage(channel=channel_id, text=message)
    except Exception as e:
        print(f"Failed to send warning message to {channel_id}: {e}")

# Helper to fetch conversation context with rate limit handling
def fetch_conversation_context(channel, message_ts, context_limit=20):
    """
    Fetches the conversation context for a given channel and message timestamp, with rate limit handling.
    """
    for attempt in range(3):
        try:
            response = client_slack.conversations_history(
                channel=channel,
                latest=message_ts,
                limit=context_limit,
                inclusive=True
            )
            if response["ok"]:
                return response["messages"]
            else:
                print(f"Failed to fetch conversation history: {response['error']}")
                return []
        except SlackApiError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 1))
                print(f"Rate limited. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                print(f"Slack API error: {e.response['error']}")
                return []
    print("Failed to fetch conversation history after retries.")
    return []

def send_weekly_toxicity_summaries():
    """
    Sends weekly summaries of toxicity scores to users and clears the toxicity log.
    """
    while True:
        time.sleep(7 * 24 * 60 * 60)  # wait one week
        for user_id, entries in toxicity_log.items():
            if not entries:
                continue
            avg_score = sum(e["score"] for e in entries) / len(entries)
            message = f"Hi there! Your average toxicity score this week was {avg_score:.2f}.\n"
            if avg_score >= 0.7:
                message += "It might be worth reflecting on your tone in messages. Let's keep things constructive! 💬"
            elif avg_score >= 0.4:
                message += "You're doing okay, but there's room for improvement in communication style."
            else:
                message += "Great job keeping your messages respectful and positive! 🎉"

            try:
                client_slack.chat_postMessage(channel=user_id, text=message)
            except Exception as e:
                print(f"Failed to send message to {user_id}: {e}")

        # Clear log after sending summaries
        toxicity_log.clear()

def is_reasonable_response(text, context_text, model_score, category):
    """
    Determines if a response is reasonable given the context and toxicity category.
    """
    try:
        if category != "coercive_authority":
            print(f"is_reasonable_response: Category {category} not coercive_authority, returning False")
            return False

        # If message is quoting another message and not issuing a new directive
        if '“' in text and '”' in text:
            print("is_reasonable_response: Message contains quotes, returning True")
            return True

        # If the message expresses disagreement or frustration but maintains respectful tone
        if any(word in text.lower() for word in ["frankly", "disagree", "unreasonable", "concerned", "unfair", "respectfully"]):
            if "idiot" not in text.lower() and "shut up" not in text.lower():
                print("is_reasonable_response: Message expresses respectful disagreement, returning True")
                return True

        # Allow legal references to remain unflagged
        if "attorney general" in text.lower() or "massachusetts law" in text.lower():
            print("is_reasonable_response: Message contains legal references, returning True")
            return True

        # If model score is high but message clearly indicates a willingness to comply
        if model_score < 0.8 and any(p in text.lower() for p in ["i'm willing to", "i remain open to", "i will comply once", "i just need"]):
            print("is_reasonable_response: Message indicates willingness to comply, returning True")
            return True

        print("is_reasonable_response: No reason to consider message reasonable, returning False")
        return False
    except Exception as e:
        print(f"Error in is_reasonable_response: {e}")
        return False

# --- Main entry point for processing Slack messages ---
def handle_slack_event(payload):
    """
    Main entry point for handling Slack events, processes and classifies messages for toxicity.
    """
    def get_message_history(channel, message_ts):
        """
        Retrieves message history for a given channel and timestamp.
        """
        try:
            response = client_slack.conversations_history(
                channel=channel,
                latest=message_ts,
                limit=20,
                inclusive=True
            )
            if response["ok"]:
                return response
            else:
                print(f"Failed to fetch conversation history: {response['error']}")
                return None
        except Exception as e:
            print(f"Failed to fetch conversation history: {e}")
            return None

    history = {}
    if not signature_verifier.is_valid_request(request.data, request.headers):
        abort(400, "Invalid request signature")

    if "challenge" in payload:
        return jsonify({"challenge": payload["challenge"]})

    event = payload.get("event", {})
    if event.get("type") == "message" and not event.get("bot_id"):
        user_id = event.get("user")
        text = event.get("text")
        channel = event.get("channel")
        thread_ts = event.get("ts")

        print(f"Evaluating message: {text}")

        # Skip warning if message contains legal justification
        if contains_legal_justification(text):
            print("Message contains legal justification, skipping further checks.")
            return make_response("", 200)

        # Explicit threat detection (reintroduced)
        explicit_threats = [
            "vou te demitir", "você está demitido", "isso vai custar caro",
            "vai se arrepender", "te coloco na rua", "não vai mais trabalhar aqui"
        ]

        threat_phrases = [
            "vou te demitir", "isso vai custar caro", "vai se arrepender",
            "vai ter consequências", "isso não vai ficar assim", "isso pode custar o emprego",
            "posso acabar com sua carreira", "isso vai te prejudicar", "vai pagar caro por isso",
            "tome cuidado com o que está fazendo", "sei onde você mora"
        ]
        THREAT_SIM_THRESHOLD = 0.72
        threat_embeddings = sbert_model.encode(threat_phrases, convert_to_tensor=True)

        lowered_text = text.lower() if text else ""

        explicit_threat = any(phrase in lowered_text for phrase in explicit_threats)
        print(f"Flags: explicit_threat={explicit_threat}")

        if explicit_threat:
            send_warning_to_slack(
                channel,
                f":rotating_light: <@{user_id}>, sua mensagem contém uma ameaça explícita. Esse tipo de linguagem não é apropriado."
            )
            return make_response("", 200)

        # Check implicit threats by semantic similarity
        try:
            input_embedding = sbert_model.encode(text, convert_to_tensor=True)
            cos_scores = util.cos_sim(input_embedding, threat_embeddings)
            max_score = float(cos_scores.max())
            implicit_threat = max_score > THREAT_SIM_THRESHOLD
            print(f"Flags: implicit_threat={implicit_threat} with max_score={max_score}")
        except Exception as e:
            print(f"Error during implicit threat detection: {e}")
            implicit_threat = False

        if implicit_threat:
            send_warning_to_slack(
                channel,
                f":warning: <@{user_id}>, sua mensagem pode conter uma ameaça explícita ou implícita. Por favor, reconsidere o tom."
            )
            return make_response("", 200)

        # Check abusive language
        try:
            abusive_flag = is_inappropriate_language(text)
            print(f"Flags: abusive={abusive_flag}")
        except Exception as e:
            print(f"Error during abusive language detection: {e}")
            abusive_flag = False

        # Fetch conversation history for context
        try:
            history = get_message_history(channel, thread_ts)
        except Exception as e:
            if isinstance(e, SlackApiError) and getattr(e.response, "data", {}).get("error") == "ratelimited":
                print("⚠️ Slack API rate limited. Proceeding without conversation context.")
            else:
                print(f"⚠️ Failed to fetch Slack history: {e}")
            history = {"messages": []}  # Proceed with empty context
        context_text = " ".join(
            f"{m.get('user', '')}: {m['text']}"
            for m in reversed(history.get("messages", []))
            if "bot_id" not in m and "text" in m
        ) if isinstance(history, dict) and "messages" in history else text

        print(f"Context window: {context_text}")

        # Call the OpenAI model to classify toxicity
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": GPT_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": context_text
                    }
                ],
                temperature=0.2
            )
            import json

            raw = response.choices[0].message.content.strip()

            if raw.startswith("```json"):
                raw = raw.removeprefix("```json").removesuffix("```").strip()

            result = json.loads(raw)
            print(f"Model response: {result}")
        except Exception as e:
            print(f"Failed to parse model response JSON or call model: {e}")
            return make_response("", 200)

        # If scores dict is empty and not abusive, skip processing
        flags = {
            "abusive": abusive_flag,
            "explicit_threat": explicit_threat,
            "implicit_threat": implicit_threat,
        }
        if not result.get("scores") and not flags["abusive"]:
            print("No scores found in model response and not abusive, skipping further processing.")
            return make_response("", 200)

        # Debug: print the final scores before checking whether to send a warning
        print(f"DEBUG: Final scores = {result.get('scores', {})}")

        scores = result.get("scores", {})
        triggered = result.get("triggered", [])

        # --- Consolidated warning logic: only send one warning per message, prioritizing by severity ---

        # Determine which categories are triggered
        categories = set()
        if flags.get("abusive") or scores.get("aggression", 0) >= AGGRESSION_THRESHOLD or scores.get("harassment", 0) >= HARASSMENT_THRESHOLD or scores.get("condescension", 0) >= CONDESCENSION_THRESHOLD:
            categories.add("abusive")
        if scores.get("threat", 0) >= THREAT_THRESHOLD:
            categories.add("threat")
        if scores.get("coercive_authority", 0) >= COERCIVE_AUTHORITY_THRESHOLD:
            categories.add("coercive")

        # Prioritize threat > coercive > abusive
        # Prioritize threat warning over others to prevent duplicate messages
        if "threat" in categories:
            categories = {"threat"}
        elif "coercive" in categories:
            categories = {"coercive"}
        elif "abusive" in categories:
            categories = {"abusive"}

        warning_message = None
        if "threat" in categories:
            warning_message = f":rotating_light: <@{user_id}>, sua mensagem contém uma ameaça. Esse tipo de linguagem não é apropriado."
        elif "coercive" in categories:
            warning_message = f":warning: <@{user_id}>, sua mensagem contém autoridade excessiva. Por favor, mantenha o respeito."
        elif "abusive" in categories:
            warning_message = f":warning: <@{user_id}>, sua mensagem contém linguagem abusiva ou ofensiva. Por favor, mantenha o respeito."

        if warning_message:
            send_warning_to_slack(channel, warning_message)
            print(f"⚠️ Warning sent to {user_id}: {warning_message}")
            return make_response("OK", 200)

        print("No category matched above threshold, skipping.")
        return make_response("", 200)

    if not hasattr(handle_slack_event, "summary_thread_started"):
        handle_slack_event.summary_thread_started = True
        Thread(target=send_weekly_toxicity_summaries, daemon=True).start()

    # Fallback: always return a valid Flask response
    return jsonify({"status": "event processed"}), 200
