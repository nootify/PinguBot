FROM python:3.8.2
COPY . .
RUN python -m pip install -r requirements.txt
CMD python pingu.py