ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3 tzdata
COPY server.py baza.py obliczenia.py ladowania.py fuelio.py /app/
COPY www /app/www
CMD ["python3", "-u", "/app/server.py"]
