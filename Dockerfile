FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Add src to PYTHONPATH so python can find authsvc
ENV PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y build-essential openssl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use the new settings path. 
# Also updated the CMD to correct manage.py usage with the module path implicitly via python manage.py
# Or better: python manage.py directly since we are in /app and manage.py is there.
CMD ["bash", "-lc", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
