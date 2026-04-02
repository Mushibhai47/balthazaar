from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func
from database.models import db, Client, Competitor, Query, Report, SubscriptionTier, ShareableLink, APICredential
from config import Config
from countries import COUNTRIES
from datetime import datetime
import json
import secrets

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

with app.app_context():
    db.create_all()
    seed_default_tiers()
    # Migration: add portal_token column if it doesn't exist yet
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN portal_token VARCHAR(64)"))
            conn.commit()
    except Exception:
        pass  # Column already exists
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE clients ADD COLUMN report_recipients TEXT DEFAULT '[]'"))
            conn.commit()
    except Exception:
        pass  # Column already exists


# --- Dashboard ---
@app.route("/")
def dashboard():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    total_reports = db.session.query(func.count(Report.id)).scalar() or 0
    total_competitors = db.session.query(func.count(Competitor.id)).scalar() or 0
    total_queries = db.session.query(func.count(Query.id)).scalar() or 0
    recent_reports = (Report.query
        .filter_by(status='complete')
        .order_by(Report.generated_at.desc())
        .limit(5).all())
    return render_template("dashboard.html", clients=clients, total_reports=total_reports,
        total_competitors=total_competitors, total_queries=total_queries,
        recent_reports=recent_reports)


# --- New Client + Intake Form ---
@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "GET":
        tiers = SubscriptionTier.query.filter_by(is_active=True).order_by(SubscriptionTier.sort_order).all()
        return render_template("intake_form.html", countries=COUNTRIES, tiers=tiers)

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

    # Create client
    client = Client(
        name=client_name,
        website=client_website,
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

    if request.method == "GET":
        tiers = SubscriptionTier.query.filter_by(is_active=True).order_by(SubscriptionTier.sort_order).all()
        return render_template("edit_client.html", client=client, tiers=tiers)

    client.name = request.form.get("client_name", client.name).strip()
    client.website = request.form.get("client_website", client.website).strip()
    client.contact_name = request.form.get("contact_name", client.contact_name).strip()
    client.contact_email = request.form.get("contact_email", client.contact_email).strip()
    client.subscription_tier = request.form.get("subscription_tier", client.subscription_tier)
    recipients_raw = request.form.get("report_recipients", "")
    extra_emails = [e.strip() for e in recipients_raw.replace(',', '\n').split('\n') if e.strip() and '@' in e]
    client.set_report_recipients(extra_emails)

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

    # Create new report
    report = Report(query_id=query.id, status="pending")
    db.session.add(report)
    db.session.commit()

    # Run in background thread (no Redis/Celery required)
    t = threading.Thread(target=run_report_sync, args=(report.id,), daemon=True)
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
        return render_template("public_intake.html", countries=COUNTRIES, tiers=tiers, token=token)

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

    client = Client(
        name=client_name,
        website=client_website,
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
    return render_template("settings.html", tiers=tiers, smtp_config=smtp_config)


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


# --- Glossary / How It Works ---
@app.route("/glossary")
def glossary():
    return render_template("glossary.html")


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
