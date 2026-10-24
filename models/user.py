from werkzeug.security import check_password_hash, generate_password_hash

from db import db


class User(db.Model):
    __tablename__ = "users"

    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role     = db.Column(db.String(20), default="Analyst")
    # Comma-separated list of page keys the user can access
    # e.g. "dashboard,recommendations"
    # Admin users always bypass this and get full access.
    modules  = db.Column(db.Text, default="dashboard,recommendations")

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def is_admin(self):
        return self.role == "Admin"
