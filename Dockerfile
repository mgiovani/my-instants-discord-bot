FROM python:3.12-slim-bookworm

# OS dependencies
RUN apt-get -y update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# App dependencies
COPY requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt

# App code
ADD . /app/
WORKDIR /app

ENTRYPOINT ["python", "-m", "bot.run"]
