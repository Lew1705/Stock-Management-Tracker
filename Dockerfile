FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src
ENV STOCK_TIMEZONE=Europe/London
ENV PORT=8080

CMD ["python", "-m", "stock.web"]
