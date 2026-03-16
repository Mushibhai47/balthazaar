"""
Celery tasks for background keyword data collection
"""
from celery_app import celery
from database.models import db, Report, Query, APICredential
from app_factory import create_app
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

# All collectors: credentials_required=False means they run without DB credentials
COLLECTORS_CONFIG = [
    {"name": "openai",          "module": "sources.openai_keywords",    "class": "OpenAICollector",         "credentials_required": True},
    {"name": "google_gemini",   "module": "sources.gemini_keywords",    "class": "GeminiCollector",         "credentials_required": True},
    {"name": "youtube",         "module": "sources.youtube_keywords",   "class": "YouTubeCollector",        "credentials_required": True},
    {"name": "tiktok",          "module": "sources.tiktok_keywords",    "class": "TikTokCollector",         "credentials_required": True},
    {"name": "instagram",       "module": "sources.instagram_keywords", "class": "InstagramCollector",      "credentials_required": True},
    {"name": "ubersuggest",     "module": "sources.ubersuggest",        "class": "UbersuggestCollector",    "credentials_required": True},
    {"name": "google_ads",      "module": "sources.google_ads_keywords","class": "GoogleAdsCollector",      "credentials_required": True},
    # Meta ads uses instagram credentials (access_token)
    {"name": "ads_tracker",     "module": "sources.ads_tracker",        "class": "AdsTrackerCollector",     "credentials_required": True,  "use_credentials_from": "instagram"},
    # Sentiment uses youtube credentials but can work without
    {"name": "sentiment",       "module": "sources.sentiment_analyzer", "class": "SentimentCollector",      "credentials_required": False, "use_credentials_from": "youtube"},
    # Free sources - no credentials needed
    {"name": "google_news",     "module": "sources.google_news",        "class": "GoogleNewsCollector",     "credentials_required": False},
    {"name": "wayback_machine", "module": "sources.wayback_machine",    "class": "WaybackMachineCollector", "credentials_required": False},
    {"name": "linkedin_jobs",   "module": "sources.linkedin_jobs",      "class": "LinkedInJobsCollector",   "credentials_required": False},
]


@celery.task(bind=True, name="tasks.generate_keyword_report")
def generate_keyword_report(self, report_id: int):
    """Background task to collect data from all sources and build the report"""
    app = create_app()
    with app.app_context():
        try:
            report = Report.query.get(report_id)
            if not report:
                return {"error": "Report not found"}

            report.status = "running"
            db.session.commit()

            query = Query.query.get(report.query_id)
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

                    # Determine which credentials to load
                    cred_service = cfg.get("use_credentials_from", source_name)
                    cred = APICredential.query.filter_by(service_name=cred_service, is_active=True).first()

                    if cfg["credentials_required"] and not cred:
                        logger.warning(f"No credentials for {source_name}, skipping")
                        report_data["metadata"]["sources_failed"].append(source_name)
                        report_data["metadata"]["errors"][source_name] = "No credentials configured"
                        continue

                    # Build credentials dict with context
                    cred_dict = cred.get_credentials() if cred else {}
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
            report = Report.query.get(report_id)
            if report:
                report.status = "failed"
                db.session.commit()
            return {"error": str(e)}
