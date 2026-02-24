from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import func
from database.models import db, Client, Competitor, Query, Report
from config import Config
from datetime import datetime
import json

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()


# --- Dashboard ---
@app.route("/")
def dashboard():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    total_reports = db.session.query(func.count(Report.id)).scalar() or 0
    total_competitors = db.session.query(func.count(Competitor.id)).scalar() or 0
    total_queries = db.session.query(func.count(Query.id)).scalar() or 0
    return render_template("dashboard.html", clients=clients, total_reports=total_reports, total_competitors=total_competitors, total_queries=total_queries)


# --- New Client + Intake Form ---
@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "GET":
        return render_template("intake_form.html")

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

    db.session.commit()
    flash(f"Client '{client_name}' created with {len(keywords)} keywords and {len(countries)} countries.", "success")
    return redirect(url_for("dashboard"))


# --- View Client ---
@app.route("/clients/<int:client_id>")
def view_client(client_id):
    client = Client.query.get_or_404(client_id)
    report_count = sum(len(q.reports) for q in client.queries)
    return render_template("client_detail.html", client=client, report_count=report_count)


# --- Edit Client ---
@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == "GET":
        return render_template("edit_client.html", client=client)

    client.name = request.form.get("client_name", client.name).strip()
    client.website = request.form.get("client_website", client.website).strip()
    client.contact_name = request.form.get("contact_name", client.contact_name).strip()
    client.contact_email = request.form.get("contact_email", client.contact_email).strip()
    client.subscription_tier = request.form.get("subscription_tier", client.subscription_tier)

    db.session.commit()
    flash(f"Client '{client.name}' updated.", "success")
    return redirect(url_for("view_client", client_id=client.id))


# --- Delete Client ---
@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    name = client.name
    db.session.delete(client)
    db.session.commit()
    flash(f"Client '{name}' and all associated data deleted.", "success")
    return redirect(url_for("dashboard"))


# --- Run Report (placeholder for future milestones) ---
@app.route("/queries/<int:query_id>/run", methods=["POST"])
def run_report(query_id):
    query = Query.query.get_or_404(query_id)
    report = Report(query_id=query.id, status="pending")
    db.session.add(report)
    db.session.commit()
    flash("Report queued. Data collection will begin when sources are connected (Milestone 2+).", "success")
    return redirect(url_for("view_client", client_id=query.client_id))


# --- Toggle Auto-Run ---
@app.route("/queries/<int:query_id>/toggle-auto", methods=["POST"])
def toggle_auto(query_id):
    query = Query.query.get_or_404(query_id)
    query.auto_run = not query.auto_run
    db.session.commit()
    status = "enabled" if query.auto_run else "disabled"
    flash(f"Auto-run {status} for this query.", "success")
    return redirect(url_for("view_client", client_id=query.client_id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
