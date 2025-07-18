# from transformers import AutoTokenizer, AutoModelForSequenceClassification
# import torch
# import torch.nn.functional as F

# class ToxicityModel:
#     def __init__(self, model_name="unitary/toxic-bert"):
#         self.tokenizer = AutoTokenizer.from_pretrained(model_name)
#         self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
#         self.labels = [
#             "toxicity", "severe_toxicity", "obscene",
#             "identity_attack", "insult", "threat", "sexual_explicit"
#         ]
    
#     def predict(self, text):
#         inputs = self.tokenizer(
#             text,
#             return_tensors="pt",
#             truncation=True,
#             max_length=512,
#             padding=True
#         )
#         with torch.no_grad():
#             outputs = self.model(**inputs)
#             scores = F.sigmoid(outputs.logits)[0].tolist()

#         return dict(zip(self.labels, scores))

#     def is_toxic(self, text, threshold=0.5):
#         scores = self.predict(text)
#         toxic_labels = {label: score for label, score in scores.items() if score > threshold}
#         return toxic_labels

#     def top_labels(self, text, top_n=3):
#         scores = self.predict(text)
#         return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]