ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3 && (apk add --no-cache py3-paho-mqtt || echo "MQTT library not available")
COPY server.py /app/server.py
COPY www /app/www
COPY firmware /app/firmware
CMD ["python3", "-u", "/app/server.py"]
