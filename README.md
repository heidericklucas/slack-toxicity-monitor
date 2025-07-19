# Slack Toxicity Monitor

This is a Kubernetes-deployed Slack app that analyzes messages in real time and uses OpenAI's GPT-4o to detect toxicity or harmful intent. When a user sends a threatening or offensive message in a Slack channel where this app is present, they receive a warning—giving them the opportunity to reflect and revise before causing harm.

## Features

- Detects offensive, threatening, or toxic messages in real time.
- Warns users directly in Slack before messages escalate further.
- Uses OpenAI's GPT-4o for nuanced language understanding.
- Deployed on Kubernetes via Minikube.
- Secrets are securely managed using Bitnami Sealed Secrets.

## Tech Stack

- **FastAPI**: Python web framework used for the app backend.
- **Slack API**: For receiving and responding to messages.
- **OpenAI GPT-4o**: For analyzing message content.
- **Kubernetes + Minikube**: Container orchestration and local testing environment.
- **Sealed Secrets**: For encrypting Slack and OpenAI API keys.

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/heidericklucas/slack-toxicity-monitor.git
   cd slack-toxicity-monitor
   ```

2. Reseal secrets with your own credentials:

   If you're planning to deploy this yourself, generate sealed secrets using your own tokens:

   ```bash
   kubectl create secret generic slack-secret \
     --dry-run=client \
     --from-literal=SLACK_SIGNING_SECRET='your-signing-secret' \
     --from-literal=SLACK_BOT_TOKEN='your-bot-token' \
     -o yaml | \
   kubeseal \
     --controller-name=sealed-secrets-controller \
     --controller-namespace=default \
     --format yaml > k8s/slack-secret-sealed.yaml

   kubectl create secret generic openai-secret \
     --dry-run=client \
     --from-literal=OPENAI_API_KEY='your-api-key' \
     -o yaml | \
   kubeseal \
     --controller-name=sealed-secrets-controller \
     --controller-namespace=default \
     --format yaml > k8s/openai-secret-sealed.yaml
   ```

3. Apply the manifests:

   ```bash
   kubectl apply -f k8s/
   ```

4. Start the service tunnel:

   ```bash
   minikube service slack-toxicity-monitor
   ```

## Demo

This project was built as a portfolio demonstration. You can view the logs and outputs locally by running:

```bash
kubectl logs deployment/slack-toxicity-monitor
```

## License

MIT