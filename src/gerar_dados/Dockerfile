FROM python:3.12-slim

# Logs aparecem na hora no docker logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala as dependencias antes de copiar o codigo para aproveitar o cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
