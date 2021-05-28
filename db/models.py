from db import db


class Clown(db.Model):
    __tablename__ = "clowns"
    guild_id = db.Column(db.Numeric, primary_key=True)
    clown_id = db.Column(db.Numeric)
    previous_clown_id = db.Column(db.Numeric)
    nomination_date = db.Column(db.Date(), server_default=db.func.now())
    join_time = db.Column(db.DateTime)


class Reminder(db.Model):
    __tablename__ = "reminders"
    reminder_id = db.Column(db.Integer(), primary_key=True)
    reminder_text = db.Column(db.Unicode)
    reminder_time = db.Column(db.DateTime)
    user_id = db.Column(db.Numeric)
    channel_id = db.Column(db.Numeric)
