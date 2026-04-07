FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src
ENV STOCK_TIMEZONE=Europe/London
ENV STOCK_TASK=dashboard

CMD ["python", "-m", "stock.railway_runner"]
