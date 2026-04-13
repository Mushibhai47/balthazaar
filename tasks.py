"""
Celery tasks for background keyword data collection
"""
from celery_app import celery
from database.models import db, Report, Query, APICredential
from app_factory import create_app
from datetime import datetime, timedelta
import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# Env var fallback for credentials (used when DB credentials aren't saved)
ENV_CREDENTIAL_MAP = {
    'openai':        {'api_key': 'OPENAI_API_KEY'},
    'google_gemini': {'api_key': 'GEMINI_API_KEY'},
    'youtube':       {'api_key': 'YOUTUBE_API_KEY'},
    'tiktok':        {'client_key': 'TIKTOK_CLIENT_KEY', 'client_secret': 'TIKTOK_CLIENT_SECRET'},
    'instagram':     {'access_token': 'INSTAGRAM_ACCESS_TOKEN', 'app_id': 'INSTAGRAM_APP_ID', 'app_secret': 'INSTAGRAM_APP_SECRET'},
    'ubersuggest':   {'email': 'UBERSUGGEST_EMAIL', 'password': 'UBERSUGGEST_PASSWORD', 'bearer_token': 'UBERSUGGEST_BEARER_TOKEN'},
    'google_ads':    {'developer_token': 'GOOGLE_ADS_DEVELOPER_TOKEN', 'client_id': 'GOOGLE_ADS_CLIENT_ID',
                      'client_secret': 'GOOGLE_ADS_CLIENT_SECRET', 'refresh_token': 'GOOGLE_ADS_REFRESH_TOKEN',
                      'customer_id': 'GOOGLE_ADS_CUSTOMER_ID'},
}


def load_credentials(service_name: str):
    """Load credentials from DB first, fall back to environment variables.
    Always supplements with any env-var fields missing from the DB record
    (e.g. bearer_token that was added to ENV_CREDENTIAL_MAP after the DB row
    was created)."""
    db_creds = None
    cred = APICredential.query.filter_by(service_name=service_name, is_active=True).first()
    if cred:
        try:
            db_creds = cred.get_credentials()
        except Exception as e:
            logger.warning(f"Failed to decrypt credentials for {service_name}: {e}")

    # Build env-var credentials for this service
    env_map = ENV_CREDENTIAL_MAP.get(service_name, {})
    env_creds = {}
    if env_map:
        env_creds = {field: os.environ.get(env_var, '') for field, env_var in env_map.items()}

    if db_creds is not None:
        # Merge: DB values take precedence; supplement any missing fields from env
        for field, value in env_creds.items():
            if value and not db_creds.get(field):
                db_creds[field] = value
        return db_creds

    if env_creds and any(v for v in env_creds.values()):
        logger.info(f"[{service_name}] Using credentials from environment variables")
        return env_creds

    return None

# All collectors: credentials_required=False means they run without DB credentials
COLLECTORS_CONFIG = [
    {"name": "openai",          "module": "sources.openai_keywords",    "class": "OpenAICollector",         "credentials_required": True},
    {"name": "google_gemini",   "module": "sources.gemini_keywords",    "class": "GeminiCollector",         "credentials_required": True},
    {"name": "youtube",         "module": "sources.youtube_keywords",   "class": "YouTubeCollector",        "credentials_required": True},
    {"name": "tiktok",          "module": "sources.tiktok_keywords",    "class": "TikTokCollector",         "credentials_required": True},
    {"name": "instagram",       "module": "sources.instagram_keywords", "class": "InstagramCollector",      "credentials_required": True},
    {"name": "ubersuggest",     "module": "sources.ubersuggest",        "class": "UbersuggestCollector",    "credentials_required": True},
    {"name": "website_traffic", "module": "sources.ubersuggest_traffic", "class": "UbersuggestTrafficCollector", "credentials_required": True, "use_credentials_from": "ubersuggest"},
    {"name": "ai_visibility",   "module": "sources.ubersuggest_ai_visibility", "class": "UbersuggestAIVisibilityCollector", "credentials_required": True, "use_credentials_from": "ubersuggest"},
    {"name": "google_ads",      "module": "sources.google_ads_keywords","class": "GoogleAdsCollector",      "credentials_required": True},
    # Meta ads uses instagram credentials (access_token)
    {"name": "ads_tracker",     "module": "sources.ads_tracker",        "class": "AdsTrackerCollector",     "credentials_required": True,  "use_credentials_from": "instagram"},
    # Sentiment uses youtube credentials but can work without
    {"name": "sentiment",       "module": "sources.sentiment_analyzer", "class": "SentimentCollector",      "credentials_required": False, "use_credentials_from": "youtube"},
    # Free sources - no credentials needed
    {"name": "google_news",     "module": "sources.google_news",        "class": "GoogleNewsCollector",     "credentials_required": False},
    {"name": "wayback_machine", "module": "sources.wayback_machine",    "class": "WaybackMachineCollector", "credentials_required": False},
    {"name": "linkedin_jobs",   "module": "sources.linkedin_jobs",      "class": "LinkedInJobsCollector",   "credentials_required": False},
    {"name": "reviews",         "module": "sources.reviews_collector",  "class": "ReviewsCollector",        "credentials_required": False},
    # AI Executive Summary — runs last, requires OpenAI
    {"name": "ai_insights",     "module": "sources.ai_insights",        "class": "AIInsightsCollector",     "credentials_required": True,  "use_credentials_from": "openai"},
]


def send_report_email(report, client, query, report_data, note='', extra_recipients=None):
    """Send report completion email to the client contact"""
    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASSWORD', '')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_from = os.environ.get('SMTP_FROM', smtp_user)
    base_url = os.environ.get('BASE_URL', '')

    if not smtp_host or not smtp_user or not smtp_pass:
        try:
            smtp_cred = APICredential.query.filter_by(service_name='smtp', is_active=True).first()
            if smtp_cred:
                sc = smtp_cred.get_credentials()
                smtp_host = sc.get('host', smtp_host)
                smtp_user = sc.get('user', smtp_user)
                smtp_pass = sc.get('password', smtp_pass)
                smtp_port = int(sc.get('port', smtp_port))
                smtp_from = sc.get('from', '') or smtp_user
                base_url = sc.get('base_url', base_url)
        except Exception:
            pass

    if not smtp_host or not smtp_user or not smtp_pass:
        logger.info("SMTP not configured — skipping email notification")
        return
    to_email = client.contact_email
    to_name = client.contact_name
    # Additional recipients (can include dozens of emails)
    stored = client.get_report_recipients() if hasattr(client, 'get_report_recipients') else []
    one_off = extra_recipients or []
    all_recipients = list({to_email} | set(stored) | set(one_off))  # deduplicate
    # Always BCC Balthazaar
    bcc_email = os.environ.get('BALTHAZAAR_EMAIL', 'hello@balthazaar.net')

    meta = report_data.get('metadata', {})
    succeeded = len(meta.get('sources_succeeded', []))
    kw_data = report_data.get('keywords', {})
    ai_data = kw_data.get('openai', kw_data.get('google_gemini', {}))
    keywords = query.get_keywords()
    rising = sum(1 for kw in keywords if ai_data.get(kw, {}).get('trend') == 'rising')
    cpc_vals = [ai_data.get(kw, {}).get('estimated_cpc', 0) for kw in keywords if ai_data.get(kw, {}).get('estimated_cpc', 0) > 0]
    avg_cpc = round(sum(cpc_vals) / len(cpc_vals), 2) if cpc_vals else 0.0
    portal_path = f"/portal/{client.portal_token}" if client.portal_token else f"/reports/{report.id}"
    report_url = f"{base_url.rstrip('/')}{portal_path}" if base_url else portal_path
    date_str = report.generated_at.strftime('%B %d, %Y') if report.generated_at else datetime.utcnow().strftime('%B %d, %Y')

    # Build keyword rows for email
    kw_rows = ""
    for kw in keywords[:8]:
        kd = ai_data.get(kw, {})
        vol = '{:,}'.format(kd.get('search_volume', 0)) if kd.get('search_volume', 0) > 0 else '—'
        cpc = f"${kd.get('estimated_cpc', 0):.2f}" if kd.get('estimated_cpc', 0) > 0 else '—'
        trend = {'rising': '↑', 'declining': '↓', 'stable': '→'}.get(kd.get('trend', ''), '—')
        trend_color = {'rising': '#16a34a', 'declining': '#dc2626', 'stable': '#94a3b8'}.get(kd.get('trend', ''), '#94a3b8')
        kw_rows += f"""<tr><td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;font-weight:600">{kw}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{vol}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{cpc}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:center;color:{trend_color};font-weight:700">{trend}</td></tr>"""

    # Add note to email if provided
    note_html = f'<div style="background:#f5f3ff;border-left:4px solid #6B51F0;padding:16px;border-radius:0 8px 8px 0;margin-bottom:28px"><p style="color:#374151;font-size:14px;margin:0;font-style:italic">"{note}"</p></div>' if note else ''

    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f8f7ff;font-family:'Helvetica Neue',Arial,sans-serif">
<div style="max-width:600px;margin:40px auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(107,81,240,0.08)">
  <div style="background:linear-gradient(135deg,#6B51F0,#8B5CF6);padding:36px 40px;text-align:center">
    <div style="font-size:11px;font-weight:700;color:rgba(255,255,255,0.7);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px">Balthazaar Intelligence</div>
    <h1 style="color:white;margin:0;font-size:24px;font-weight:700">Your Report is Ready</h1>
    <p style="color:rgba(255,255,255,0.8);margin:8px 0 0;font-size:14px">{client.name} — {date_str}</p>
  </div>
  <div style="padding:36px 40px">
    <p style="color:#374151;font-size:15px;margin:0 0 24px">Hi {to_name},</p>
    <p style="color:#374151;font-size:14px;line-height:1.6;margin:0 0 28px">Your latest competitive intelligence report has been generated with data from <strong>{succeeded} sources</strong>.</p>
    {note_html}
    <div style="display:flex;gap:12px;margin-bottom:28px">
      <div style="flex:1;background:#f5f3ff;border-radius:12px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#6B51F0">{len(keywords)}</div>
        <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em">Keywords</div>
      </div>
      <div style="flex:1;background:#f0fdf4;border-radius:12px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#16a34a">{rising}</div>
        <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em">Rising</div>
      </div>
      <div style="flex:1;background:#fffbeb;border-radius:12px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#d97706">${avg_cpc}</div>
        <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em">Avg CPC</div>
      </div>
      <div style="flex:1;background:#f0f9ff;border-radius:12px;padding:16px;text-align:center">
        <div style="font-size:28px;font-weight:700;color:#0284c7">{succeeded}/15</div>
        <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em">Sources</div>
      </div>
    </div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:28px;font-size:13px">
      <thead><tr style="background:#f8f7ff">
        <th style="padding:10px 12px;text-align:left;font-size:10px;color:#6B51F0;text-transform:uppercase;letter-spacing:0.06em">Keyword</th>
        <th style="padding:10px 12px;text-align:right;font-size:10px;color:#6B51F0;text-transform:uppercase;letter-spacing:0.06em">Volume</th>
        <th style="padding:10px 12px;text-align:right;font-size:10px;color:#6B51F0;text-transform:uppercase;letter-spacing:0.06em">CPC</th>
        <th style="padding:10px 12px;text-align:center;font-size:10px;color:#6B51F0;text-transform:uppercase;letter-spacing:0.06em">Trend</th>
      </tr></thead>
      <tbody>{kw_rows}</tbody>
    </table>
    <div style="text-align:center;margin-bottom:28px">
      <a href="{report_url}" style="display:inline-block;background:linear-gradient(135deg,#6B51F0,#8B5CF6);color:white;text-decoration:none;padding:14px 36px;border-radius:12px;font-weight:700;font-size:15px">View Full Report →</a>
    </div>
    <p style="color:#94a3b8;font-size:12px;text-align:center;margin:0">This is an automated report from Balthazaar Intelligence. Keep this email private.</p>
  </div>
</div></body></html>"""

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{client.name}] Intelligence Report Ready — {date_str}"
        msg['From'] = f"Balthazaar Intelligence <{smtp_from}>"
        msg['To'] = f"{to_name} <{to_email}>"
        if len(all_recipients) > 1:
            msg['CC'] = ', '.join(r for r in all_recipients if r != to_email)
        msg['Bcc'] = bcc_email
        msg.attach(MIMEText(html, 'html'))
        send_to = list(set(all_recipients + [bcc_email]))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, send_to, msg.as_string())
        logger.info(f"Report email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send report email: {e}")


def send_new_client_notification(client, keywords, countries):
    """Send notification to hello@balthazaar.net when a new client form is submitted"""
    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASSWORD', '')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_from = os.environ.get('SMTP_FROM', smtp_user)
    notify_to = os.environ.get('BALTHAZAAR_EMAIL', 'hello@balthazaar.net')

    if not smtp_host or not smtp_user or not smtp_pass:
        logger.info("SMTP not configured — skipping new client notification")
        return

    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f8f7ff;padding:40px">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(107,81,240,0.1)">
  <div style="background:linear-gradient(135deg,#6B51F0,#8B5CF6);padding:28px 36px">
    <h1 style="color:white;margin:0;font-size:20px">New Client Form Submitted</h1>
    <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;font-size:13px">Balthazaar Intelligence Platform</p>
  </div>
  <div style="padding:28px 36px">
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
      <tr><td style="padding:8px 0;color:#94a3b8;font-weight:600;width:140px">Client Name</td><td style="padding:8px 0;color:#1a1a2e;font-weight:700">{client.name}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;font-weight:600">Website</td><td style="padding:8px 0;color:#6B51F0">{client.website}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;font-weight:600">Contact</td><td style="padding:8px 0;color:#374151">{client.contact_name} &lt;{client.contact_email}&gt;</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;font-weight:600">Keywords</td><td style="padding:8px 0;color:#374151">{len(keywords)} keywords</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;font-weight:600">Countries</td><td style="padding:8px 0;color:#374151">{', '.join(countries)}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;font-weight:600">Tier</td><td style="padding:8px 0;color:#374151">{client.subscription_tier}</td></tr>
    </table>
    <p style="font-size:12px;color:#94a3b8;margin:0">Log in to the dashboard to review and run the first report.</p>
  </div>
</div></body></html>"""

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"New Client: {client.name} — Form Submitted"
        msg['From'] = f"Balthazaar Intelligence <{smtp_from}>"
        msg['To'] = notify_to
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [notify_to], msg.as_string())
        logger.info(f"New client notification sent to {notify_to}")
    except Exception as e:
        logger.error(f"Failed to send new client notification: {e}")


def run_report_sync(report_id: int, country_override: str = None):
    """Run report generation synchronously (used by threading fallback when Redis unavailable)"""
    app = create_app()
    with app.app_context():
        _do_generate_report(report_id, country_override=country_override)


def _compute_historical_trends(current_report, query, report_data: dict, country_override: str = None):
    """
    Look at the last 6 completed reports for this query (same country) and
    compute a data-driven trend for each keyword based on actual volume history.
    Overwrites the 'trend' field in every keyword source dict.
    """
    # Fetch up to 6 previous complete reports for same query + country
    q = (db.session.query(Report)
         .filter(Report.query_id == query.id,
                 Report.status == 'complete',
                 Report.id != current_report.id))
    if country_override:
        q = q.filter(Report.country == country_override)
    past_reports = q.order_by(Report.created_at.desc()).limit(5).all()

    if not past_reports:
        logger.info("No historical reports found — skipping trend computation")
        return  # Not enough history yet

    def _extract_volumes(rdata: dict) -> dict:
        """Return {keyword: volume} from a report's data blob."""
        kw_block = rdata.get('keywords', {})
        # Prefer AI sources (most consistent volume data)
        for src in ('openai', 'google_gemini', 'ubersuggest', 'google_ads'):
            src_data = kw_block.get(src, {})
            if isinstance(src_data, dict) and src_data:
                return {k: v.get('search_volume', 0) for k, v in src_data.items() if isinstance(v, dict)}
        return {}

    # Build time series: newest first (index 0 = most recent past, index 4 = oldest)
    history = []
    for r in past_reports:
        try:
            rdata = json.loads(r.data) if r.data else {}
            history.append(_extract_volumes(rdata))
        except Exception:
            history.append({})

    current_volumes = _extract_volumes(report_data)

    for keyword, cur_vol in current_volumes.items():
        if cur_vol == 0:
            continue
        # Collect all available volume points (current + up to 5 past), newest first
        series = [cur_vol] + [h.get(keyword, 0) for h in history]
        series = [v for v in series if v > 0]  # drop zeros

        if len(series) < 2:
            continue  # Not enough data points

        # Linear trend: compare average of first half vs average of second half
        mid = len(series) // 2
        recent_avg = sum(series[:mid]) / mid
        older_avg = sum(series[mid:]) / (len(series) - mid)

        if older_avg == 0:
            continue

        change_pct = (recent_avg - older_avg) / older_avg * 100

        if change_pct > 8:
            trend = 'rising'
        elif change_pct < -8:
            trend = 'declining'
        else:
            trend = 'stable'

        # Overwrite trend in every keyword source that has this keyword
        kw_block = report_data.get('keywords', {})
        for src_name, src_data in kw_block.items():
            if isinstance(src_data, dict) and keyword in src_data:
                if isinstance(src_data[keyword], dict):
                    src_data[keyword]['trend'] = trend
                    src_data[keyword]['trend_pct'] = round(change_pct, 1)
                    src_data[keyword]['trend_periods'] = len(series)

    # ── Website traffic trend ──────────────────────────────────────────
    traffic_block = report_data.get('keywords', {}).get('website_traffic', {})
    if traffic_block:
        for domain_key, td in traffic_block.items():
            if not isinstance(td, dict):
                continue
            cur_total = td.get('total_monthly', 0)
            if cur_total == 0:
                continue
            hist_vals = []
            for r in past_reports:
                try:
                    rd = json.loads(r.data) if r.data else {}
                    past_td = rd.get('keywords', {}).get('website_traffic', {}).get(domain_key, {})
                    v = past_td.get('total_monthly', 0) if isinstance(past_td, dict) else 0
                    if v > 0:
                        hist_vals.append(v)
                except Exception:
                    pass
            series = [cur_total] + hist_vals
            if len(series) < 2:
                continue
            mid = len(series) // 2
            recent_avg = sum(series[:mid]) / mid
            older_avg = sum(series[mid:]) / (len(series) - mid)
            if older_avg == 0:
                continue
            change_pct = (recent_avg - older_avg) / older_avg * 100
            td['trend'] = 'rising' if change_pct > 8 else ('declining' if change_pct < -8 else 'stable')
            td['trend_pct'] = round(change_pct, 1)

    # ── Sentiment trend ────────────────────────────────────────────────
    sentiment_block = report_data.get('keywords', {}).get('sentiment', {})
    if sentiment_block:
        for sent_key, sd in sentiment_block.items():
            if not isinstance(sd, dict):
                continue
            cur_pos = sd.get('positive_pct', 0)
            hist_pos = []
            for r in past_reports:
                try:
                    rd = json.loads(r.data) if r.data else {}
                    past_sd = rd.get('keywords', {}).get('sentiment', {}).get(sent_key, {})
                    v = past_sd.get('positive_pct', 0) if isinstance(past_sd, dict) else 0
                    if v > 0:
                        hist_pos.append(v)
                except Exception:
                    pass
            series = [cur_pos] + hist_pos
            if len(series) < 2:
                continue
            mid = len(series) // 2
            recent_avg = sum(series[:mid]) / mid
            older_avg = sum(series[mid:]) / (len(series) - mid)
            if older_avg == 0:
                continue
            change_pct = (recent_avg - older_avg) / older_avg * 100
            sd['sentiment_trend'] = 'rising' if change_pct > 5 else ('declining' if change_pct < -5 else 'stable')
            sd['sentiment_trend_pct'] = round(change_pct, 1)

    periods_used = len(past_reports) + 1  # past + current
    report_data["metadata"]["trend_periods_used"] = periods_used
    logger.info(f"Historical trend computed from {len(past_reports)} past report(s) ({periods_used} total periods)")


def _do_generate_report(report_id: int, country_override: str = None):
    """Core report generation logic — called by both Celery task and thread fallback"""
    try:
            report = db.session.get(Report, report_id)
            if not report:
                return {"error": "Report not found"}

            report.status = "running"
            db.session.commit()

            query = db.session.get(Query, report.query_id)
            if not query:
                report.status = "failed"
                db.session.commit()
                return {"error": "Query not found"}

            keywords = query.get_keywords()
            all_countries = query.get_countries()
            # Use only the specific country for this report, if set
            countries = [country_override] if country_override else all_countries
            client = query.client

            logger.info(f"Generating report for {len(keywords)} keywords across {len(countries)} countries")

            # Build competitor context to pass to all collectors
            context = {
                '_client_name': client.name,
                '_client_website': client.website,
                '_client_youtube': getattr(client, 'youtube_url', '') or '',
                '_client_review_url': getattr(client, 'review_page_url', '') or '',
                '_competitors': [
                    {
                        'name': c.name,
                        'website': c.website,
                        'youtube_url': c.youtube_url or '',
                        'review_page_url': getattr(c, 'review_page_url', '') or ''
                    }
                    for c in client.competitors
                ]
            }

            report_data = {
                "version": "2.0",
                "keywords": {},
                "metadata": {
                    "collected_at": datetime.utcnow().isoformat(),
                    "client_name": client.name,
                    "country": country_override,
                    "countries": countries,
                    "sources_succeeded": [],
                    "sources_failed": [],
                    "errors": {},
                    "progress": 0
                }
            }

            total = len(COLLECTORS_CONFIG)
            completed = 0

            for cfg in COLLECTORS_CONFIG:
                source_name = cfg["name"]
                try:
                    logger.info(f"Collecting data from {source_name}...")

                    # Determine which credentials to load (DB first, then env vars)
                    cred_service = cfg.get("use_credentials_from", source_name)
                    cred_dict = load_credentials(cred_service)

                    if cfg["credentials_required"] and not cred_dict:
                        logger.warning(f"No credentials for {source_name}, skipping")
                        report_data["metadata"]["sources_failed"].append(source_name)
                        report_data["metadata"]["errors"][source_name] = "No credentials configured"
                        continue

                    cred_dict = cred_dict or {}
                    cred_dict.update(context)  # Inject competitor/client context

                    # Dynamically import and run collector
                    mod = __import__(cfg["module"], fromlist=[cfg["class"]])
                    CollectorClass = getattr(mod, cfg["class"])
                    collector = CollectorClass(cred_dict)
                    result = collector.safe_collect(keywords, countries)

                    if result["success"]:
                        report_data["keywords"][source_name] = result["data"]
                        report_data["metadata"]["sources_succeeded"].append(source_name)
                        logger.info(f"Successfully collected from {source_name}")
                    else:
                        report_data["metadata"]["sources_failed"].append(source_name)
                        report_data["metadata"]["errors"][source_name] = result.get("error", "Unknown error")
                        logger.error(f"Failed to collect from {source_name}: {result.get('error')}")

                except Exception as e:
                    logger.error(f"Error with {source_name}: {str(e)}")
                    report_data["metadata"]["sources_failed"].append(source_name)
                    report_data["metadata"]["errors"][source_name] = str(e)

                finally:
                    completed += 1
                    report_data["metadata"]["progress"] = int(completed / total * 100)
                    report.data = json.dumps(report_data)
                    db.session.commit()

            if report_data["metadata"]["sources_succeeded"]:
                # Compute data-driven 6-period trend before finalising
                try:
                    _compute_historical_trends(report, query, report_data, country_override)
                except Exception as e:
                    logger.warning(f"Historical trend computation failed (non-fatal): {e}")

                report.status = "complete"
                report.generated_at = datetime.utcnow()
                logger.info(f"Report {report_id} complete — {len(report_data['metadata']['sources_succeeded'])} sources succeeded")
                # Send email notification
                try:
                    send_report_email(report, client, query, report_data)
                except Exception as e:
                    logger.warning(f"Email notification failed (non-fatal): {e}")
            else:
                report.status = "failed"
                logger.error(f"Report {report_id} failed — no sources succeeded")

            report.data = json.dumps(report_data)
            db.session.commit()

            return {
                "report_id": report_id,
                "status": report.status,
                "sources_succeeded": len(report_data["metadata"]["sources_succeeded"]),
                "sources_failed": len(report_data["metadata"]["sources_failed"])
            }

    except Exception as e:
        logger.error(f"Fatal error on report {report_id}: {str(e)}")
        try:
            report = db.session.get(Report, report_id)
            if report:
                report.status = "failed"
                db.session.commit()
        except Exception:
            pass


@celery.task(bind=True, name="tasks.generate_keyword_report")
def generate_keyword_report(self, report_id: int, country_override: str = None):
    """Celery task wrapper — delegates to core logic"""
    app = create_app()
    with app.app_context():
        _do_generate_report(report_id, country_override=country_override)


@celery.task(name="tasks.run_scheduled_reports")
def run_scheduled_reports():
    """Hourly task: auto-run reports for queries with auto_run=True that are due"""
    app = create_app()
    with app.app_context():
        triggered = 0
        queries = Query.query.filter_by(auto_run=True).all()
        for query in queries:
            # Get the most recent report for this query
            last_report = (db.session.query(Report)
                           .filter(Report.query_id == query.id)
                           .order_by(Report.created_at.desc())
                           .first())

            # Determine interval in hours based on frequency
            interval_hours = {
                'daily': 24,
                'weekly': 168,
                'fortnightly': 336,
                'monthly': 720,
            }.get(query.frequency, 720)

            should_run = False
            if not last_report:
                should_run = True
            elif last_report.status not in ('pending', 'running'):
                hours_since = (datetime.utcnow() - last_report.created_at).total_seconds() / 3600
                should_run = hours_since >= interval_hours

            if should_run:
                countries = query.get_countries()
                if len(countries) > 1:
                    # Create one report per country
                    for country in countries:
                        report = Report(query_id=query.id, status="pending", country=country)
                        db.session.add(report)
                        db.session.flush()
                        db.session.commit()
                        generate_keyword_report.delay(report.id, country)
                    logger.info(f"Auto-triggered {len(countries)} country reports for query {query.id} (client: {query.client.name})")
                else:
                    country = countries[0] if countries else None
                    report = Report(query_id=query.id, status="pending", country=country)
                    db.session.add(report)
                    db.session.commit()
                    generate_keyword_report.delay(report.id, country)
                    logger.info(f"Auto-triggered report for query {query.id} (client: {query.client.name})")
                triggered += 1

        logger.info(f"Scheduled reports check complete — {triggered} reports triggered")
        return {"triggered": triggered}
