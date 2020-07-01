FROM python:3.8.3
COPY . .
RUN python -m pip install -r requirements.txt
CMD python pingu.py