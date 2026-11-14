# Obraz bazowy wieloarchitekturowy (amd64 i arm64) – zamiast build.yaml, który HA wycofuje (wpis HA z 2.04.2026).
FROM ghcr.io/home-assistant/base:3.22
LABEL \
    io.hass.type="addon" \
    io.hass.name="Pojazdy" \
    org.opencontainers.image.title="Pojazdy" \
    org.opencontainers.image.description="Tankowania, ładowania, koszty, terminy, polisy i opony pojazdów" \
    org.opencontainers.image.source="https://github.com/pbnz7nrwm4-hub/nt1100-ha"
RUN apk add --no-cache python3 tzdata
COPY server.py baza.py obliczenia.py ladowania.py fuelio.py opony.py prognoza.py /app/
COPY www /app/www
CMD ["python3", "-u", "/app/server.py"]
