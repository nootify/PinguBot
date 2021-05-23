from db import db


class Clown(db.Model):
    __tablename__ = "clowns"
    guild_id = db.Column(db.Numeric, primary_key=True)
    clown_id = db.Column(db.Numeric)
    previous_clown_id = db.Column(db.Numeric)
    nomination_date = db.Column(db.Date(), server_default="now()")
    join_time = db.Column(db.DateTime)
