# Slack Toxicity Monitor

A Slack app that flags threatening or offensive messages in real time. The project uses OpenAI's GPT-4o to analyze language so users can receive a gentle warning before conversations escalate.

## Features

- Detects aggression, harassment, or threats in Slack channels.
- Posts a warning in the same channel and tags the author.
- Works with Kubernetes via Minikube for easy local testing.
- Secrets are stored using Bitnami Sealed Secrets.

## Tech Stack

- **Flask** – Lightweight Python web framework powering the API.
- **Slack SDK** – Receives events and posts messages back to Slack.
- **OpenAI GPT-4o** – Provides nuanced toxicity classification.
- **Kubernetes** – Deployment target with accompanying manifests.

## Prerequisites

Create a Slack app and obtain the following credentials:

- `SLACK_SIGNING_SECRET`
- `SLACK_BOT_TOKEN`
- `OPENAI_API_KEY`

You can copy `.env.example` and populate it with your values.

## Running Locally

Install dependencies and start the Flask server:

```bash
pip install -r requirements.txt
python app/main.py
```

Alternatively, build and run the Docker image:

```bash
docker build -t slack-toxicity-monitor .
docker run -p 5000:5000 --env-file .env slack-toxicity-monitor
```

The app will be available on `http://localhost:5000`.

## Kubernetes Deployment

If you want to try the project on Minikube:

1. Reseal the Kubernetes secrets with your credentials:

   ```bash
   kubectl create secret generic slack-secret \
     --dry-run=client \
     --from-literal=SLACK_SIGNING_SECRET='your-signing-secret' \
     --from-literal=SLACK_BOT_TOKEN='your-bot-token' \
     -o yaml | kubeseal \
     --controller-name=sealed-secrets-controller \
     --controller-namespace=default \
     --format yaml > k8s/slack-secret-sealed.yaml

   kubectl create secret generic openai-secret \
     --dry-run=client \
     --from-literal=OPENAI_API_KEY='your-api-key' \
     -o yaml | kubeseal \
     --controller-name=sealed-secrets-controller \
     --controller-namespace=default \
     --format yaml > k8s/openai-secret-sealed.yaml
   ```

2. Apply the manifests:

   ```bash
   kubectl apply -f k8s/
   ```

3. Expose the service:

   ```bash
   minikube service slack-toxicity-monitor
   ```

## Logs

You can inspect activity via:

```bash
kubectl logs deployment/slack-toxicity-monitor
```

## License

MIT
