from python:3.9.0-slim-buster


# OS dependencies
RUN apt-get -y update
RUN apt-get -y upgrade
RUN apt-get install -y ffmpeg

# App dependencies
ADD . /app/
WORKDIR /app
RUN pip install -r requirements.txt

ENTRYPOINT ["PYTHONPATH=.", "python", "bot/run.py"]
