FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app app
COPY backend/migrate.py /app/migrate.py
COPY db/migrations /migrations
COPY backend/start.sh /usr/local/bin/careguard-start
RUN chmod +x /usr/local/bin/careguard-start \
    && addgroup --system careguard \
    && adduser --system --ingroup careguard careguard \
    && chown -R careguard:careguard /app
USER careguard
EXPOSE 8000
CMD ["careguard-start"]
