from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func
from database.models import db, Client, Competitor, Query, Report, SubscriptionTier, ShareableLink, APICredential, GlossarySection
from config import Config
from countries import COUNTRIES
from datetime import datetime
import json
import secrets
import logging
import os

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def seed_default_tiers():
    """Create default subscription tiers if they don't exist"""
    if SubscriptionTier.query.count() == 0:
        default_tiers = [
            SubscriptionTier(
                name="Trial",
                slug="trial",
                price=0.0,
                duration_months=0,
                sort_order=1,
                features=json.dumps(["1 competitor", "Basic reports", "Monthly frequency"])
            ),
            SubscriptionTier(
                name="6 Month Package",
                slug="6month",
                price=1200.0,
                duration_months=6,
                sort_order=2,
                features=json.dumps(["Up to 10 competitors", "Full reports", "Fortnightly frequency", "Auto-run"])
            ),
            SubscriptionTier(
                name="1 Year Package",
                slug="1year",
                price=2000.0,
                duration_months=12,
                sort_order=3,
                features=json.dumps(["Unlimited competitors", "Premium reports", "Custom frequency", "Auto-run", "Priority support"])
            ),
        ]
        for tier in default_tiers:
            db.session.add(tier)
        db.session.commit()

DEFAULT_GLOSSARY = [
    {'icon': 'psychology', 'color': 'text-brand', 'title': 'ChatGPT Overall Market Score', 'source': 'Powered by OpenAI GPT-4o', 'description': 'A score from 0–100 reflecting the overall competitive strength of a brand. Calculated by GPT-4o after analysing keyword trends, search volume, competition levels, CPC data, news sentiment, and competitor activity. A higher score indicates stronger market presence and opportunity. Scores are generated for the client and each selected competitor independently.', 'fields': ['0–40: Weak market presence', '41–65: Moderate, room to grow', '66–80: Strong competitive position', '81–100: Market leader']},
    {'icon': 'search', 'color': 'text-indigo-500', 'title': 'Keyword Volume & Trends', 'source': 'OpenAI / Google Gemini', 'description': 'Monthly search volume estimates for each tracked keyword. Trend direction (↑ rising / — stable / ↓ declining) reflects whether search interest is increasing or decreasing. CPC (Cost Per Click) shows the estimated advertising cost for that keyword.', 'fields': ['Volume: estimated monthly searches', 'Avg. Volume: 6-month average', 'CPC: estimated Google Ads cost per click', 'Competition: LOW / MEDIUM / HIGH']},
    {'icon': 'bar_chart', 'color': 'text-indigo-600', 'title': 'Website Traffic', 'source': 'Ubersuggest', 'description': 'Estimated monthly website visits pulled from Ubersuggest for the client and each competitor. Split into organic (SEO-driven) and paid (advertising-driven) traffic.', 'fields': ['Organic: visits from search engines (unpaid)', 'Paid: visits from paid advertising', 'Domain Score: overall domain authority (0–100)']},
    {'icon': 'play_circle', 'color': 'text-red-500', 'title': 'YouTube Performance', 'source': 'YouTube Data API', 'description': 'Video performance data fetched via the official YouTube API. Shows how content related to tracked keywords is performing — total videos, average views, engagement rates, and which channels dominate each topic.', 'fields': ['Avg Views: average views per video', 'Engagement Rate: (likes + comments) / views × 100', 'Competition: how saturated the keyword is on YouTube']},
    {'icon': 'sentiment_satisfied', 'color': 'text-purple-500', 'title': 'Online Sentiment', 'source': 'Google News + VADER NLP', 'description': 'Sentiment analysis of online content mentioning the brand or keywords. Uses VADER (Valence Aware Dictionary and sEntiment Reasoner), a proven NLP model, to score each piece of content as Positive, Neutral, or Negative. Brand sentiment searches specifically for the client and competitor brand names.', 'fields': ['Positive: favourable mentions', 'Neutral: factual/balanced mentions', 'Negative: critical or unfavourable mentions', 'Score range: -1.0 (most negative) to +1.0 (most positive)']},
    {'icon': 'newspaper', 'color': 'text-blue-500', 'title': 'Brand Monitoring & News', 'source': 'Google News RSS', 'description': 'Latest news articles mentioning the brand name or competitor names, fetched from Google News. Articles are sorted by recency. Provides real-time visibility into press coverage, announcements, and media mentions.', 'fields': ['Brand search: searches by exact brand/company name', 'Top 5 articles shown per brand', 'Source, date, and direct link provided']},
    {'icon': 'history', 'color': 'text-amber-500', 'title': 'Website Amendments', 'source': 'Internet Archive', 'description': 'Detects changes to competitor websites by comparing historical snapshots. Identifies when pages were updated, added, or restructured — giving insight into product launches, pricing changes, and strategic shifts.', 'fields': ['Snapshot comparison over 30-day window', 'Page-level change detection', 'Direct link to historical version for comparison']},
    {'icon': 'work', 'color': 'text-blue-700', 'title': 'Recruitment Intelligence', 'source': 'LinkedIn Jobs', 'description': 'Tracks job postings from competitors on LinkedIn. Hiring patterns reveal strategic direction — a competitor hiring data scientists signals AI investment; hiring sales staff signals market expansion.', 'fields': ['Role title and location', 'Date posted', 'Link to full job listing']},
    {'icon': 'campaign', 'color': 'text-blue-600', 'title': 'Adverts — Meta & Google', 'source': 'Meta Ad Library API / Google Ads API', 'description': 'Active advertising campaigns run by the brand and competitors. Meta Ad Library is publicly accessible. Google Ads data requires API access. Shows what messaging and offers competitors are actively promoting.', 'fields': ['Advertiser name', 'Campaign start date', 'Estimated impressions', 'Link to view the ad creative']},
]


def seed_default_glossary():
    """Seed glossary sections with defaults if table is empty"""
    if GlossarySection.query.count() == 0:
        for i, s in enumerate(DEFAULT_GLOSSARY):
            section = GlossarySection(
                title=s['title'], source=s['source'], description=s['description'],
                icon=s['icon'], color=s['color'], sort_order=i
            )
            section.set_fields(s['fields'])
            db.session.add(section)
        db.session.commit()


with app.app_context():
    db.create_all()
    seed_default_tiers()
    # Migrations
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN portal_token VARCHAR(64)"))
            conn.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN report_recipients TEXT DEFAULT '[]'"))
            conn.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE reports ADD COLUMN country VARCHAR(100)"))
            conn.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN youtube_url VARCHAR(500) DEFAULT ''"))
            conn.commit()
    except Exception:
        pass
    seed_default_glossary()


# --- Dashboard ---
@app.route("/")
def dashboard():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    total_reports = db.session.query(func.count(Report.id)).scalar() or 0
    total_competitors = db.session.query(func.count(Competitor.id)).scalar() or 0
    total_queries = db.session.query(func.count(Query.id)).scalar() or 0
    recent_reports = (db.session.query(Report)
        .filter_by(status='complete')
        .order_by(Report.generated_at.desc())
        .limit(5).all())
    return render_template("dashboard.html", clients=clients, total_reports=total_reports,
        total_competitors=total_competitors, total_queries=total_queries,
        recent_reports=recent_reports)


def _get_links_config():
    """Return NDA and contract URLs from DB or env vars."""
    try:
        cred = APICredential.query.filter_by(service_name='links').first()
        if cred:
            return cred.get_credentials()
    except Exception:
        pass
    return {
        'nda_url': os.environ.get('NDA_URL', ''),
        'contract_url': os.environ.get('CONTRACT_URL', ''),
    }


# --- New Client + Intake Form ---
@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "GET":
        tiers = SubscriptionTier.query.filter_by(is_active=True).order_by(SubscriptionTier.sort_order).all()
        return render_template("intake_form.html", countries=COUNTRIES, tiers=tiers, links=_get_links_config())

    # Parse form data
    client_name = request.form.get("client_name", "").strip()
    client_website = request.form.get("client_website", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    subscription_tier = request.form.get("subscription_tier", "trial")

    if not client_name or not client_website or not contact_name or not contact_email:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("new_client"))

    # Client social handles
    platforms = request.form.getlist("social_platform[]")
    handles = request.form.getlist("social_handle[]")
    social_handles = []
    for p, h in zip(platforms, handles):
        if h.strip():
            social_handles.append({"platform": p, "handle": h.strip()})

    client_youtube = request.form.get("client_youtube", "").strip()

    # Create client
    client = Client(
        name=client_name,
        website=client_website,
        youtube_url=client_youtube,
        contact_name=contact_name,
        contact_email=contact_email,
        subscription_tier=subscription_tier,
    )
    client.set_social_handles(social_handles)
    db.session.add(client)
    db.session.flush()  # get client.id

    # Competitors
    comp_names = request.form.getlist("comp_name[]")
    comp_websites = request.form.getlist("comp_website[]")
    comp_youtubes = request.form.getlist("comp_youtube[]")
    comp_vimeos = request.form.getlist("comp_vimeo[]")
    comp_reviews = request.form.getlist("comp_review[]")

    for i in range(len(comp_websites)):
        if not comp_websites[i].strip():
            continue
        # Competitor social handles
        comp_platforms = request.form.getlist(f"comp_social_platform_{i}[]")
        comp_handles = request.form.getlist(f"comp_social_handle_{i}[]")
        comp_socials = []
        for p, h in zip(comp_platforms, comp_handles):
            if h.strip():
                comp_socials.append({"platform": p, "handle": h.strip()})

        comp = Competitor(
            client_id=client.id,
            name=comp_names[i].strip() if i < len(comp_names) else "",
            website=comp_websites[i].strip(),
            youtube_url=comp_youtubes[i].strip() if i < len(comp_youtubes) else "",
            vimeo_url=comp_vimeos[i].strip() if i < len(comp_vimeos) else "",
            review_page_url=comp_reviews[i].strip() if i < len(comp_reviews) else "",
        )
        comp.set_social_handles(comp_socials)
        db.session.add(comp)

    # Keywords
    keywords_raw = request.form.get("keywords", "")
    keywords = [k.strip() for k in keywords_raw.split("\n") if k.strip()]
    if len(keywords) > 1000:
        keywords = keywords[:1000]

    # Countries
    countries = [c for c in request.form.getlist("countries[]") if c]

    # Reporting settings
    frequency = request.form.get("frequency", "monthly")
    auto_run = bool(request.form.get("auto_run"))
    period_start = request.form.get("period_start")
    period_end = request.form.get("period_end")

    query = Query(
        client_id=client.id,
        frequency=frequency,
        auto_run=auto_run,
        period_start=datetime.strptime(period_start, "%Y-%m-%d").date() if period_start else None,
        period_end=datetime.strptime(period_end, "%Y-%m-%d").date() if period_end else None,
    )
    query.set_keywords(keywords)
    query.set_countries(countries)
    db.session.add(query)

    # Report recipients
    recipients_raw = request.form.get("report_recipients", "")
    extra_emails = [e.strip() for e in recipients_raw.replace(',', '\n').split('\n') if e.strip() and '@' in e]
    client.set_report_recipients(extra_emails)

    db.session.commit()

    # Notify hello@balthazaar.net that a new client form was submitted
    try:
        from tasks import send_new_client_notification
        send_new_client_notification(client, keywords, countries)
    except Exception as e:
        logger.warning(f"New client notification failed: {e}")

    flash(f"Client '{client_name}' created with {len(keywords)} keywords and {len(countries)} countries.", "success")
    return redirect(url_for("dashboard"))


# --- View Client ---
@app.route("/clients/<int:client_id>")
def view_client(client_id):
    client = db.get_or_404(Client, client_id)
    report_count = sum(len(q.reports) for q in client.queries)
    return render_template("client_detail.html", client=client, report_count=report_count)


# --- Edit Client ---
@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    client = db.get_or_404(Client, client_id)

    query = client.queries[0] if client.queries else None

    if request.method == "GET":
        tiers = SubscriptionTier.query.filter_by(is_active=True).order_by(SubscriptionTier.sort_order).all()
        return render_template("edit_client.html", client=client, tiers=tiers, query=query, countries=COUNTRIES)

    client.name = request.form.get("client_name", client.name).strip()
    client.website = request.form.get("client_website", client.website).strip()
    client.youtube_url = request.form.get("client_youtube", getattr(client, 'youtube_url', '') or '').strip()
    client.contact_name = request.form.get("contact_name", client.contact_name).strip()
    client.contact_email = request.form.get("contact_email", client.contact_email).strip()
    client.subscription_tier = request.form.get("subscription_tier", client.subscription_tier)
    recipients_raw = request.form.get("report_recipients", "")
    extra_emails = [e.strip() for e in recipients_raw.replace(',', '\n').split('\n') if e.strip() and '@' in e]
    client.set_report_recipients(extra_emails)

    # Update query keywords and countries
    if query:
        keywords_raw = request.form.get("keywords", "")
        new_keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]
        if new_keywords:
            query.set_keywords(new_keywords)
        new_countries = [c for c in request.form.getlist("countries[]") if c.strip()]
        if new_countries:
            query.set_countries(new_countries)

    # Update competitor fields
    for comp in client.competitors:
        comp_name = request.form.get(f"comp_name_{comp.id}", "").strip()
        comp_website = request.form.get(f"comp_website_{comp.id}", "").strip()
        comp_youtube = request.form.get(f"comp_youtube_{comp.id}", "").strip()
        comp_review = request.form.get(f"comp_review_{comp.id}", "").strip()
        if comp_name:
            comp.name = comp_name
        if comp_website:
            comp.website = comp_website
        comp.youtube_url = comp_youtube
        comp.review_page_url = comp_review

    db.session.commit()
    flash(f"Client '{client.name}' updated.", "success")
    return redirect(url_for("view_client", client_id=client.id))


# --- Delete Client ---
@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    client = db.get_or_404(Client, client_id)
    name = client.name
    db.session.delete(client)
    db.session.commit()
    flash(f"Client '{name}' and all associated data deleted.", "success")
    return redirect(url_for("dashboard"))


# --- View Report ---
@app.route("/reports/<int:report_id>")
def view_report(report_id):
    report = db.get_or_404(Report, report_id)
    query = report.query
    client = query.client
    keywords = query.get_keywords()
    try:
        data = json.loads(report.data) if report.data else {}
    except json.JSONDecodeError:
        data = {}
    kw_data = data.get('keywords', {})
    ai_data = kw_data.get('openai', kw_data.get('google_gemini', {}))
    rising_count = sum(1 for kw in keywords if ai_data.get(kw, {}).get('trend') == 'rising')
    cpc_vals = [ai_data.get(kw, {}).get('estimated_cpc', 0) for kw in keywords if ai_data.get(kw, {}).get('estimated_cpc', 0) > 0]
    avg_cpc = round(sum(cpc_vals) / len(cpc_vals), 2) if cpc_vals else 0.0
    metadata = data.get('metadata', {})

    competitors = client.competitors
    return render_template("report_detail.html",
        report=report, query=query, client=client,
        data=data, keywords=keywords,
        rising_count=rising_count, avg_cpc=avg_cpc,
        metadata=metadata, competitors=competitors
    )


# --- Run Report ---
@app.route("/queries/<int:query_id>/run", methods=["POST"])
def run_report(query_id):
    import threading
    from tasks import run_report_sync

    query = db.get_or_404(Query, query_id)
    countries = query.get_countries()

    if len(countries) > 1:
        # Create one report per country and run each in its own thread
        for country in countries:
            report = Report(query_id=query.id, status="pending", country=country)
            db.session.add(report)
            db.session.flush()  # get report.id before commit
            db.session.commit()
            t = threading.Thread(target=run_report_sync, args=(report.id, country), daemon=True)
            t.start()
        flash(f"Report generation started for {len(countries)} countries! Data is being collected from all sources.", "success")
    else:
        # Single country (or none set) — run one combined report
        country = countries[0] if countries else None
        report = Report(query_id=query.id, status="pending", country=country)
        db.session.add(report)
        db.session.commit()
        t = threading.Thread(target=run_report_sync, args=(report.id, country), daemon=True)
        t.start()
        flash("Report generation started! Data is being collected from all sources.", "success")

    return redirect(url_for("view_client", client_id=query.client_id))


# --- Report Status API (for real-time progress updates) ---
@app.route("/api/reports/<int:report_id>/status")
def report_status(report_id):
    """API endpoint to check report generation status"""
    report = db.get_or_404(Report, report_id)

    # Parse report data to get progress info
    try:
        data = json.loads(report.data) if report.data else {}
        metadata = data.get("metadata", {})
    except json.JSONDecodeError:
        metadata = {}

    return jsonify({
        "id": report.id,
        "status": report.status,
        "progress": metadata.get("progress", 0),
        "sources_succeeded": len(metadata.get("sources_succeeded", [])),
        "sources_failed": len(metadata.get("sources_failed", [])),
        "errors": metadata.get("errors", {}),
        "generated_at": report.generated_at.isoformat() if report.generated_at else None
    })


# --- Toggle Auto-Run ---
@app.route("/queries/<int:query_id>/toggle-auto", methods=["POST"])
def toggle_auto(query_id):
    query = db.get_or_404(Query, query_id)
    query.auto_run = not query.auto_run
    db.session.commit()
    status = "enabled" if query.auto_run else "disabled"
    flash(f"Auto-run {status} for this query.", "success")
    return redirect(url_for("view_client", client_id=query.client_id))


# --- Public Intake Form (Shareable Link) ---
@app.route("/intake/<token>", methods=["GET", "POST"])
def public_intake(token):
    link = ShareableLink.query.filter_by(token=token, is_active=True).first()
    if not link:
        flash("Invalid or expired form link.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        tiers = SubscriptionTier.query.filter_by(is_active=True).order_by(SubscriptionTier.sort_order).all()
        return render_template("public_intake.html", countries=COUNTRIES, tiers=tiers, token=token, links=_get_links_config())

    # Process submission (same as new_client POST logic)
    client_name = request.form.get("client_name", "").strip()
    client_website = request.form.get("client_website", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    subscription_tier = request.form.get("subscription_tier", "trial")

    if not client_name or not client_website or not contact_name or not contact_email:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("public_intake", token=token))

    platforms = request.form.getlist("social_platform[]")
    handles = request.form.getlist("social_handle[]")
    social_handles = []
    for p, h in zip(platforms, handles):
        if h.strip():
            social_handles.append({"platform": p, "handle": h.strip()})

    client_youtube = request.form.get("client_youtube", "").strip()

    client = Client(
        name=client_name,
        website=client_website,
        youtube_url=client_youtube,
        contact_name=contact_name,
        contact_email=contact_email,
        subscription_tier=subscription_tier,
    )
    client.set_social_handles(social_handles)
    db.session.add(client)
    db.session.flush()

    comp_names = request.form.getlist("comp_name[]")
    comp_websites = request.form.getlist("comp_website[]")
    comp_youtubes = request.form.getlist("comp_youtube[]")
    comp_vimeos = request.form.getlist("comp_vimeo[]")
    comp_reviews = request.form.getlist("comp_review[]")

    for i in range(len(comp_websites)):
        if not comp_websites[i].strip():
            continue
        comp_platforms = request.form.getlist(f"comp_social_platform_{i}[]")
        comp_handles = request.form.getlist(f"comp_social_handle_{i}[]")
        comp_socials = []
        for p, h in zip(comp_platforms, comp_handles):
            if h.strip():
                comp_socials.append({"platform": p, "handle": h.strip()})

        comp = Competitor(
            client_id=client.id,
            name=comp_names[i].strip() if i < len(comp_names) else "",
            website=comp_websites[i].strip(),
            youtube_url=comp_youtubes[i].strip() if i < len(comp_youtubes) else "",
            vimeo_url=comp_vimeos[i].strip() if i < len(comp_vimeos) else "",
            review_page_url=comp_reviews[i].strip() if i < len(comp_reviews) else "",
        )
        comp.set_social_handles(comp_socials)
        db.session.add(comp)

    keywords_raw = request.form.get("keywords", "")
    keywords = [k.strip() for k in keywords_raw.split("\n") if k.strip()]
    if len(keywords) > 1000:
        keywords = keywords[:1000]

    countries = [c for c in request.form.getlist("countries[]") if c]
    frequency = request.form.get("frequency", "monthly")
    auto_run = bool(request.form.get("auto_run"))
    period_start = request.form.get("period_start")
    period_end = request.form.get("period_end")

    query = Query(
        client_id=client.id,
        frequency=frequency,
        auto_run=auto_run,
        period_start=datetime.strptime(period_start, "%Y-%m-%d").date() if period_start else None,
        period_end=datetime.strptime(period_end, "%Y-%m-%d").date() if period_end else None,
    )
    query.set_keywords(keywords)
    query.set_countries(countries)
    db.session.add(query)

    link.use_count += 1
    db.session.commit()

    # Notify hello@balthazaar.net that a new client form was submitted via public link
    try:
        from tasks import send_new_client_notification
        send_new_client_notification(client, keywords, countries)
    except Exception as e:
        logger.warning(f"Public intake notification failed: {e}")

    return render_template("public_intake_success.html", client_name=client_name)


# --- Manage Shareable Links ---
@app.route("/links")
def manage_links():
    links = ShareableLink.query.order_by(ShareableLink.created_at.desc()).all()
    return render_template("manage_links.html", links=links)


@app.route("/links/new", methods=["POST"])
def create_link():
    label = request.form.get("label", "Intake Form").strip()
    token = secrets.token_urlsafe(32)
    link = ShareableLink(token=token, label=label)
    db.session.add(link)
    db.session.commit()
    flash(f"Shareable link created: {label}", "success")
    return redirect(url_for("manage_links"))


@app.route("/links/<int:link_id>/toggle", methods=["POST"])
def toggle_link(link_id):
    link = db.get_or_404(ShareableLink, link_id)
    link.is_active = not link.is_active
    db.session.commit()
    status = "activated" if link.is_active else "deactivated"
    flash(f"Link {status}.", "success")
    return redirect(url_for("manage_links"))


@app.route("/links/<int:link_id>/delete", methods=["POST"])
def delete_link(link_id):
    link = db.get_or_404(ShareableLink, link_id)
    db.session.delete(link)
    db.session.commit()
    flash("Link deleted.", "success")
    return redirect(url_for("manage_links"))


# --- Settings: Manage Subscription Tiers ---
@app.route("/settings")
def settings():
    tiers = SubscriptionTier.query.order_by(SubscriptionTier.sort_order).all()
    smtp_cred = APICredential.query.filter_by(service_name='smtp').first()
    smtp_config = {}
    if smtp_cred:
        try:
            smtp_config = smtp_cred.get_credentials()
        except Exception:
            pass
    links_cred = APICredential.query.filter_by(service_name='links').first()
    links_config = {}
    if links_cred:
        try:
            links_config = links_cred.get_credentials()
        except Exception:
            pass
    return render_template("settings.html", tiers=tiers, smtp_config=smtp_config, links_config=links_config)


@app.route("/settings/tiers/new", methods=["POST"])
def create_tier():
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip()
    price = float(request.form.get("price", 0))
    duration_months = int(request.form.get("duration_months", 0))
    features_raw = request.form.get("features", "")
    features = [f.strip() for f in features_raw.split("\n") if f.strip()]

    if not name or not slug:
        flash("Name and slug are required.", "error")
        return redirect(url_for("settings"))

    tier = SubscriptionTier(
        name=name,
        slug=slug,
        price=price,
        duration_months=duration_months,
        sort_order=SubscriptionTier.query.count() + 1
    )
    tier.set_features(features)
    db.session.add(tier)
    db.session.commit()
    flash(f"Tier '{name}' created.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/tiers/<int:tier_id>/edit", methods=["POST"])
def edit_tier(tier_id):
    tier = db.get_or_404(SubscriptionTier, tier_id)
    tier.name = request.form.get("name", tier.name).strip()
    tier.slug = request.form.get("slug", tier.slug).strip()
    tier.price = float(request.form.get("price", tier.price))
    tier.duration_months = int(request.form.get("duration_months", tier.duration_months))
    features_raw = request.form.get("features", "")
    features = [f.strip() for f in features_raw.split("\n") if f.strip()]
    tier.set_features(features)
    db.session.commit()
    flash(f"Tier '{tier.name}' updated.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/tiers/<int:tier_id>/delete", methods=["POST"])
def delete_tier(tier_id):
    tier = db.get_or_404(SubscriptionTier, tier_id)
    name = tier.name
    db.session.delete(tier)
    db.session.commit()
    flash(f"Tier '{name}' deleted.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/tiers/<int:tier_id>/toggle", methods=["POST"])
def toggle_tier(tier_id):
    tier = db.get_or_404(SubscriptionTier, tier_id)
    tier.is_active = not tier.is_active
    db.session.commit()
    status = "activated" if tier.is_active else "deactivated"
    flash(f"Tier '{tier.name}' {status}.", "success")
    return redirect(url_for("settings"))


# --- Email Report ---
@app.route("/reports/<int:report_id>/email", methods=["POST"])
def email_report(report_id):
    from tasks import send_report_email
    report = db.get_or_404(Report, report_id)
    if report.status != 'complete':
        flash("Can only email completed reports.", "error")
        return redirect(url_for("view_report", report_id=report_id))
    query = report.query
    client = query.client
    note = request.form.get('note', '').strip()
    extra_raw = request.form.get('extra_recipients', '')
    extra_emails = [e.strip() for e in extra_raw.replace(',', '\n').split('\n') if e.strip() and '@' in e]
    try:
        data = json.loads(report.data) if report.data else {}
    except json.JSONDecodeError:
        data = {}
    try:
        send_report_email(report, client, query, data, note=note, extra_recipients=extra_emails)
        all_count = 1 + len(client.get_report_recipients()) + len(extra_emails)
        flash(f"Report emailed to {all_count} recipient(s).", "success")
    except Exception as e:
        flash(f"Email failed: {str(e)}", "error")
    return redirect(url_for("view_report", report_id=report_id))


# --- Edit Executive Summary ---
@app.route("/reports/<int:report_id>/edit-summary", methods=["POST"])
def edit_summary(report_id):
    report = db.get_or_404(Report, report_id)
    try:
        data = json.loads(report.data) if report.data else {}
    except json.JSONDecodeError:
        data = {}
    kw_data = data.get('keywords', {})
    ai_data = kw_data.get('ai_insights', {})
    # Update fields from form
    ai_data['executive_summary'] = request.form.get('executive_summary', ai_data.get('executive_summary', ''))
    # Parse opportunities
    opp_titles = request.form.getlist('opp_title[]')
    opp_descs = request.form.getlist('opp_desc[]')
    opp_prios = request.form.getlist('opp_priority[]')
    if opp_titles:
        ai_data['top_opportunities'] = [
            {'title': t, 'description': d, 'priority': p}
            for t, d, p in zip(opp_titles, opp_descs, opp_prios) if t.strip()
        ]
    # Parse threats
    threat_comps = request.form.getlist('threat_comp[]')
    threat_texts = request.form.getlist('threat_text[]')
    threat_sevs = request.form.getlist('threat_severity[]')
    if threat_comps:
        ai_data['competitive_threats'] = [
            {'competitor': c, 'threat': t, 'severity': s}
            for c, t, s in zip(threat_comps, threat_texts, threat_sevs) if c.strip()
        ]
    # Parse actions
    actions = request.form.getlist('action[]')
    if actions:
        ai_data['recommended_actions'] = [a for a in actions if a.strip()]
    kw_data['ai_insights'] = ai_data
    data['keywords'] = kw_data
    report.data = json.dumps(data)
    db.session.commit()
    flash("Executive summary updated.", "success")
    return redirect(url_for("view_report", report_id=report_id))


# --- Links Settings (NDA, Contract) ---
@app.route("/settings/links", methods=["POST"])
def save_links():
    """Save NDA and contract URL settings"""
    cred = APICredential.query.filter_by(service_name='links').first()
    if not cred:
        cred = APICredential(service_name='links')
        db.session.add(cred)
    links_data = {
        'nda_url': request.form.get('nda_url', '').strip(),
        'contract_url': request.form.get('contract_url', '').strip(),
    }
    cred.set_credentials(links_data)
    db.session.commit()
    flash("Links updated successfully.", "success")
    return redirect(url_for("settings"))


# --- Admin Panel ---
@app.route("/admin")
def admin():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    total_reports = db.session.query(func.count(Report.id)).scalar() or 0
    credentials = APICredential.query.all()
    glossary_count = GlossarySection.query.filter_by(is_active=True).count()
    recent_reports = (Report.query
        .order_by(Report.created_at.desc())
        .limit(10).all())
    return render_template("admin.html",
        clients=clients,
        total_reports=total_reports,
        credentials=credentials,
        glossary_count=glossary_count,
        recent_reports=recent_reports,
    )


# --- Glossary / How It Works ---
@app.route("/glossary")
def glossary():
    sections = GlossarySection.query.filter_by(is_active=True).order_by(GlossarySection.sort_order).all()
    return render_template("glossary.html", sections=sections)


@app.route("/glossary/new", methods=["POST"])
def glossary_new():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Title is required.", "error")
        return redirect(url_for("glossary"))
    fields_raw = request.form.get("fields", "")
    fields_list = [f.strip() for f in fields_raw.splitlines() if f.strip()]
    max_order = db.session.query(func.max(GlossarySection.sort_order)).scalar() or 0
    section = GlossarySection(
        title=title,
        source=request.form.get("source", "").strip(),
        description=request.form.get("description", "").strip(),
        icon=request.form.get("icon", "info").strip() or "info",
        color=request.form.get("color", "text-brand").strip() or "text-brand",
        sort_order=max_order + 1,
    )
    section.set_fields(fields_list)
    db.session.add(section)
    db.session.commit()
    flash("Terminology section added.", "success")
    return redirect(url_for("glossary"))


@app.route("/glossary/<int:section_id>/edit", methods=["POST"])
def glossary_edit(section_id):
    section = db.get_or_404(GlossarySection, section_id)
    section.title = request.form.get("title", section.title).strip()
    section.source = request.form.get("source", section.source).strip()
    section.description = request.form.get("description", section.description).strip()
    section.icon = request.form.get("icon", section.icon).strip() or section.icon
    section.color = request.form.get("color", section.color).strip() or section.color
    fields_raw = request.form.get("fields", "")
    fields_list = [f.strip() for f in fields_raw.splitlines() if f.strip()]
    section.set_fields(fields_list)
    db.session.commit()
    flash("Section updated.", "success")
    return redirect(url_for("glossary"))


@app.route("/glossary/<int:section_id>/delete", methods=["POST"])
def glossary_delete(section_id):
    section = db.get_or_404(GlossarySection, section_id)
    db.session.delete(section)
    db.session.commit()
    flash("Section deleted.", "success")
    return redirect(url_for("glossary"))


@app.route("/glossary/reorder", methods=["POST"])
def glossary_reorder():
    order = request.json.get("order", [])
    for idx, sid in enumerate(order):
        GlossarySection.query.filter_by(id=sid).update({"sort_order": idx})
    db.session.commit()
    return jsonify({"ok": True})


# --- SMTP Settings ---
@app.route("/settings/smtp", methods=["POST"])
def save_smtp():
    """Save SMTP settings as a special APICredential entry"""
    cred = APICredential.query.filter_by(service_name='smtp').first()
    if not cred:
        cred = APICredential(service_name='smtp')
        db.session.add(cred)
    smtp_data = {
        'host': request.form.get('smtp_host', '').strip(),
        'port': request.form.get('smtp_port', '587').strip(),
        'user': request.form.get('smtp_user', '').strip(),
        'password': request.form.get('smtp_password', '').strip(),
        'from': request.form.get('smtp_from', '').strip(),
        'base_url': request.form.get('base_url', '').strip(),
    }
    cred.set_credentials(smtp_data)
    db.session.commit()
    # Also write to env for current process (Celery reads from env)
    import subprocess
    flash("SMTP settings saved. Add these as Replit Secrets for persistence.", "success")
    return redirect(url_for("settings"))


# --- PDF / Print Export ---
@app.route("/reports/<int:report_id>/print")
def print_report(report_id):
    report = db.get_or_404(Report, report_id)
    query = report.query
    client = query.client
    keywords = query.get_keywords()
    try:
        data = json.loads(report.data) if report.data else {}
    except json.JSONDecodeError:
        data = {}
    kw_data = data.get('keywords', {})
    ai_data = kw_data.get('openai', kw_data.get('google_gemini', {}))
    metadata = data.get('metadata', {})
    return render_template("report_print.html",
        report=report, query=query, client=client,
        data=data, keywords=keywords, ai_data=ai_data, metadata=metadata
    )


# --- Client Portal ---
@app.route("/clients/<int:client_id>/portal/generate", methods=["POST"])
def generate_portal(client_id):
    client = db.get_or_404(Client, client_id)
    if not client.portal_token:
        client.portal_token = secrets.token_urlsafe(32)
        db.session.commit()
    flash(f"Portal link generated for {client.name}.", "success")
    return redirect(url_for("view_client", client_id=client.id))


@app.route("/clients/<int:client_id>/portal/reset", methods=["POST"])
def reset_portal(client_id):
    client = db.get_or_404(Client, client_id)
    client.portal_token = secrets.token_urlsafe(32)
    db.session.commit()
    flash("Portal link regenerated. Old link is now invalid.", "success")
    return redirect(url_for("view_client", client_id=client.id))


@app.route("/portal/<token>")
def client_portal(token):
    client = Client.query.filter_by(portal_token=token).first()
    if not client:
        flash("Invalid or expired portal link.", "error")
        return redirect(url_for("dashboard"))
    # Get all reports sorted newest first
    all_reports = []
    for q in client.queries:
        for r in sorted(q.reports, key=lambda x: x.created_at, reverse=True):
            all_reports.append((r, q))
    return render_template("client_portal.html", client=client, all_reports=all_reports, token=token)


@app.route("/portal/<token>/reports/<int:report_id>")
def portal_report(token, report_id):
    client = Client.query.filter_by(portal_token=token).first()
    if not client:
        flash("Invalid or expired portal link.", "error")
        return redirect(url_for("dashboard"))
    report = db.get_or_404(Report, report_id)
    # Make sure report belongs to this client
    if report.query.client_id != client.id:
        flash("Access denied.", "error")
        return redirect(url_for("client_portal", token=token))
    query = report.query
    keywords = query.get_keywords()
    try:
        data = json.loads(report.data) if report.data else {}
    except json.JSONDecodeError:
        data = {}
    kw_data = data.get('keywords', {})
    ai_data = kw_data.get('openai', kw_data.get('google_gemini', {}))
    rising_count = sum(1 for kw in keywords if ai_data.get(kw, {}).get('trend') == 'rising')
    cpc_vals = [ai_data.get(kw, {}).get('estimated_cpc', 0) for kw in keywords if ai_data.get(kw, {}).get('estimated_cpc', 0) > 0]
    avg_cpc = round(sum(cpc_vals) / len(cpc_vals), 2) if cpc_vals else 0.0
    metadata = data.get('metadata', {})
    return render_template("report_detail.html",
        report=report, query=query, client=client,
        data=data, keywords=keywords,
        rising_count=rising_count, avg_cpc=avg_cpc,
        metadata=metadata, portal_token=token
    )


def run_auto_scheduled_reports():
    """Check for auto-run queries that are due and trigger reports."""
    with app.app_context():
        import threading
        from tasks import run_report_sync
        from datetime import timedelta
        queries = Query.query.filter_by(auto_run=True).all()
        triggered = 0
        for query in queries:
            last_report = (Report.query
                           .filter_by(query_id=query.id)
                           .order_by(Report.created_at.desc())
                           .first())
            interval_hours = {
                'daily': 24, 'weekly': 168, 'fortnightly': 336, 'monthly': 720,
            }.get(query.frequency, 720)
            should_run = False
            if not last_report:
                should_run = True
            elif last_report.status not in ('pending', 'running'):
                hours_since = (datetime.utcnow() - last_report.created_at).total_seconds() / 3600
                should_run = hours_since >= interval_hours
            if should_run:
                report = Report(query_id=query.id, status="pending")
                db.session.add(report)
                db.session.commit()
                t = threading.Thread(target=run_report_sync, args=(report.id,), daemon=True)
                t.start()
                triggered += 1
        if triggered:
            import logging
            logging.getLogger(__name__).info(f"Auto-scheduled {triggered} report(s)")


def start_scheduler():
    """Start APScheduler to trigger auto-run reports on a schedule."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(run_auto_scheduled_reports, 'interval', hours=1, id='auto_reports', replace_existing=True)
        scheduler.start()
        import atexit
        atexit.register(lambda: scheduler.shutdown(wait=False))
    except ImportError:
        pass  # APScheduler not installed, auto-run disabled


if __name__ == "__main__":
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=True)
