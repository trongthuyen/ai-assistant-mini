FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal; markdownify/requests are pure-python.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/assets/articles

ENTRYPOINT ["python", "main.py"]
