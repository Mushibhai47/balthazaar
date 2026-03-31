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
    'ubersuggest':   {'email': 'UBERSUGGEST_EMAIL', 'password': 'UBERSUGGEST_PASSWORD'},
    'google_ads':    {'developer_token': 'GOOGLE_ADS_DEVELOPER_TOKEN', 'client_id': 'GOOGLE_ADS_CLIENT_ID',
                      'client_secret': 'GOOGLE_ADS_CLIENT_SECRET', 'refresh_token': 'GOOGLE_ADS_REFRESH_TOKEN',
                      'customer_id': 'GOOGLE_ADS_CUSTOMER_ID'},
}


def load_credentials(service_name: str):
    """Load credentials from DB first, fall back to environment variables"""
    cred = APICredential.query.filter_by(service_name=service_name, is_active=True).first()
    if cred:
        try:
            return cred.get_credentials()
        except Exception as e:
            logger.warning(f"Failed to decrypt credentials for {service_name}: {e}")

    # Fallback to env vars
    env_map = ENV_CREDENTIAL_MAP.get(service_name, {})
    if env_map:
        creds = {field: os.environ.get(env_var, '') for field, env_var in env_map.items()}
        if any(v for v in creds.values()):  # at least one value present
            logger.info(f"[{service_name}] Using credentials from environment variables")
            return creds

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
    {"name": "google_ads",      "module": "sources.google_ads_keywords","class": "GoogleAdsCollector",      "credentials_required": True},
    # Meta ads uses instagram credentials (access_token)
    {"name": "ads_tracker",     "module": "sources.ads_tracker",        "class": "AdsTrackerCollector",     "credentials_required": True,  "use_credentials_from": "instagram"},
    # Sentiment uses youtube credentials but can work without
    {"name": "sentiment",       "module": "sources.sentiment_analyzer", "class": "SentimentCollector",      "credentials_required": False, "use_credentials_from": "youtube"},
    # Free sources - no credentials needed
    {"name": "google_news",     "module": "sources.google_news",        "class": "GoogleNewsCollector",     "credentials_required": False},
    {"name": "wayback_machine", "module": "sources.wayback_machine",    "class": "WaybackMachineCollector", "credentials_required": False},
    {"name": "linkedin_jobs",   "module": "sources.linkedin_jobs",      "class": "LinkedInJobsCollector",   "credentials_required": False},
    # AI Executive Summary — runs last, requires OpenAI
    {"name": "ai_insights",     "module": "sources.ai_insights",        "class": "AIInsightsCollector",     "credentials_required": True,  "use_credentials_from": "openai"},
]


def send_report_email(report, client, query, report_data, note=''):
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
        <div style="font-size:28px;font-weight:700;color:#0284c7">{succeeded}/13</div>
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
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_string())
        logger.info(f"Report email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send report email: {e}")


def run_report_sync(report_id: int):
    """Run report generation synchronously (used by threading fallback when Redis unavailable)"""
    app = create_app()
    with app.app_context():
        _do_generate_report(report_id)


def _do_generate_report(report_id: int):
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
            countries = query.get_countries()
            client = query.client

            logger.info(f"Generating report for {len(keywords)} keywords across {len(countries)} countries")

            # Build competitor context to pass to all collectors
            context = {
                '_client_name': client.name,
                '_client_website': client.website,
                '_competitors': [
                    {
                        'name': c.name,
                        'website': c.website,
                        'youtube_url': c.youtube_url or ''
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
def generate_keyword_report(self, report_id: int):
    """Celery task wrapper — delegates to core logic"""
    app = create_app()
    with app.app_context():
        _do_generate_report(report_id)


@celery.task(name="tasks.run_scheduled_reports")
def run_scheduled_reports():
    """Hourly task: auto-run reports for queries with auto_run=True that are due"""
    app = create_app()
    with app.app_context():
        triggered = 0
        queries = Query.query.filter_by(auto_run=True).all()
        for query in queries:
            # Get the most recent report for this query
            last_report = (Report.query
                           .filter_by(query_id=query.id)
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
                report = Report(query_id=query.id, status="pending")
                db.session.add(report)
                db.session.commit()
                generate_keyword_report.delay(report.id)
                logger.info(f"Auto-triggered report for query {query.id} (client: {query.client.name})")
                triggered += 1

        logger.info(f"Scheduled reports check complete — {triggered} reports triggered")
        return {"triggered": triggered}
