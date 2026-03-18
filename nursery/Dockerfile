FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

COPY nursery/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nursery/main.py .

CMD ["python", "-u", "main.py"]
