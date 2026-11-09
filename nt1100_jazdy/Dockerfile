ARG BUILD_FROM
FROM $BUILD_FROM
ARG BUILD_VERSION
ENV NT1100_VERSION=$BUILD_VERSION
RUN apk add --no-cache python3 && (apk add --no-cache py3-paho-mqtt || echo "MQTT library not available")
COPY server.py nav.py ntt.py graf.py adresy.py navapi.py demo-trasa.json /app/
COPY www /app/www
COPY firmware /app/firmware
CMD ["python3", "-u", "/app/server.py"]
