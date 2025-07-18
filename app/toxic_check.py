from app.models import ToxicityModel

model = ToxicityModel()

TOXICITY_THRESHOLD = 0.7 # can be adjusted based on requirements

def check_toxicity(text):
    scores = model.predict(text)
    toxic_labels = {label: score for label, score in scores.items() if score >= TOXICITY_THRESHOLD}
    is_toxic = len(toxic_labels) > 0

    return {
        "is_toxic": is_toxic,
        "scores": scores,
        "triggered": toxic_labels
    }