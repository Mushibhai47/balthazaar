from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(500), nullable=False)
    social_handles = db.Column(db.Text, default="[]")  # JSON list
    contact_name = db.Column(db.String(255), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)
    subscription_tier = db.Column(db.String(50), default="trial")  # trial, 6month, 1year
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    competitors = db.relationship("Competitor", backref="client", cascade="all, delete-orphan")
    queries = db.relationship("Query", backref="client", cascade="all, delete-orphan")

    def get_social_handles(self):
        return json.loads(self.social_handles) if self.social_handles else []

    def set_social_handles(self, handles):
        self.social_handles = json.dumps(handles)


class Competitor(db.Model):
    __tablename__ = "competitors"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    name = db.Column(db.String(255), default="")
    website = db.Column(db.String(500), nullable=False)
    social_handles = db.Column(db.Text, default="[]")  # JSON list
    youtube_url = db.Column(db.String(500), default="")
    vimeo_url = db.Column(db.String(500), default="")
    review_page_url = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_social_handles(self):
        return json.loads(self.social_handles) if self.social_handles else []

    def set_social_handles(self, handles):
        self.social_handles = json.dumps(handles)


class Query(db.Model):
    __tablename__ = "queries"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    keywords = db.Column(db.Text, default="[]")  # JSON list, up to 1000
    countries = db.Column(db.Text, default="[]")  # JSON list, up to 100
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)
    frequency = db.Column(db.String(50), default="monthly")  # monthly, fortnightly, custom
    auto_run = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reports = db.relationship("Report", backref="query", cascade="all, delete-orphan")

    def get_keywords(self):
        return json.loads(self.keywords) if self.keywords else []

    def set_keywords(self, kw_list):
        self.keywords = json.dumps(kw_list)

    def get_countries(self):
        return json.loads(self.countries) if self.countries else []

    def set_countries(self, countries_list):
        self.countries = json.dumps(countries_list)


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    query_id = db.Column(db.Integer, db.ForeignKey("queries.id"), nullable=False)
    status = db.Column(db.String(50), default="pending")  # pending, running, complete, failed
    data = db.Column(db.Text, default="{}")  # JSON blob with all scraped results
    generated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
