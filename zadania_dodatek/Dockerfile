FROM ghcr.io/home-assistant/base:3.22
LABEL \
    io.hass.type="addon" \
    io.hass.name="Zadania dzieci" \
    org.opencontainers.image.title="Zadania dzieci" \
    org.opencontainers.image.description="Panel aplikacji Zadania dzieci w Home Assistant" \
    org.opencontainers.image.source="https://github.com/pbnz7nrwm4-hub/nt1100-ha"
RUN apk add --no-cache python3 tzdata
COPY posrednik.py /app/
CMD ["python3", "-u", "/app/posrednik.py"]
