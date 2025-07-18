# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app code
COPY . .

# Expose the Flask port (adjust if different)
EXPOSE 5000

# Set PYTHONPATH so Python knows where to look for your packages
ENV PYTHONPATH=/app

# Run the Flask app
CMD ["python", "app/main.py"]