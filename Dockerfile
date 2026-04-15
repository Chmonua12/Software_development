FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sql/ ./sql/
COPY main.py .

# Скрипт инициализации БД из schema.sql
COPY init_db.sh ./init_db.sh
RUN chmod +x init_db.sh

CMD ["bash", "init_db.sh"]
