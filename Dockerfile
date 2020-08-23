FROM python:3.8.2
RUN useradd -m -G root postgres
RUN apt update
RUN apt-get -y install sudo
WORKDIR /home/postgres
RUN apt install postgresql postgresql-contrib -y

COPY . .
RUN touch pingu.log
RUN chmod 777 pingu.log
RUN chmod 777 pingu.py
RUN python -m pip install -r requirements.txt
CMD service postgresql start && sudo -u postgres psql -c "CREATE TABLE clowns (guild_id numeric(25,0) PRIMARY KEY, clown_id numeric(25,0), clowned_on date);" && sudo --preserve-env=PINGU_TOKEN -u postgres python pingu.py