ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3
COPY server.py /app/server.py
COPY www /app/www
CMD ["python3", "-u", "/app/server.py"]
