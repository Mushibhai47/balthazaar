"""
Celery tasks for background keyword data collection
"""
from celery_app import celery
from database.models import db, Report, Query, APICredential
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="tasks.generate_keyword_report")
def generate_keyword_report(self, report_id: int):
    """
    Background task to collect keyword data from all sources

    Args:
        report_id: ID of the Report to populate with data
    """
    from main import app  # Import here to avoid circular imports

    with app.app_context():
        try:
            # Get the report
            report = Report.query.get(report_id)
            if not report:
                logger.error(f"Report {report_id} not found")
                return {"error": "Report not found"}

            # Update status to running
            report.status = "running"
            db.session.commit()

            # Get the associated query
            query = Query.query.get(report.query_id)
            if not query:
                logger.error(f"Query {query.id} not found")
                report.status = "failed"
                db.session.commit()
                return {"error": "Query not found"}

            keywords = query.get_keywords()
            countries = query.get_countries()

            logger.info(f"Generating report for {len(keywords)} keywords across {len(countries)} countries")

            # Initialize report data structure
            report_data = {
                "version": "2.0",
                "keywords": {},
                "aggregated_insights": {},
                "metadata": {
                    "collected_at": datetime.utcnow().isoformat(),
                    "sources_succeeded": [],
                    "sources_failed": [],
                    "errors": {},
                    "progress": 0
                }
            }

            # List of collectors to use (will be imported dynamically as we build them)
            collectors_config = [
                {"name": "openai", "module": "sources.openai_keywords", "class": "OpenAICollector"},
                {"name": "google_gemini", "module": "sources.gemini_keywords", "class": "GeminiCollector"},
                {"name": "youtube", "module": "sources.youtube_keywords", "class": "YouTubeCollector"},
                {"name": "tiktok", "module": "sources.tiktok_keywords", "class": "TikTokCollector"},
                {"name": "instagram", "module": "sources.instagram_keywords", "class": "InstagramCollector"},
                {"name": "ubersuggest", "module": "sources.ubersuggest", "class": "UbersuggestCollector"},
                # Note: Google Ads collector requires complex OAuth setup, implement later
            ]

            total_collectors = len(collectors_config)
            completed_collectors = 0

            # Collect data from each source
            for collector_config in collectors_config:
                try:
                    source_name = collector_config["name"]
                    logger.info(f"Collecting data from {source_name}...")

                    # Get API credentials for this source
                    cred = APICredential.query.filter_by(service_name=source_name, is_active=True).first()
                    if not cred:
                        logger.warning(f"No credentials found for {source_name}, skipping")
                        report_data["metadata"]["sources_failed"].append(source_name)
                        report_data["metadata"]["errors"][source_name] = "No credentials configured"
                        continue

                    # Dynamically import the collector
                    module = __import__(collector_config["module"], fromlist=[collector_config["class"]])
                    CollectorClass = getattr(module, collector_config["class"])

                    # Instantiate and run collector
                    collector = CollectorClass(cred.get_credentials())
                    result = collector.safe_collect(keywords, countries)

                    if result["success"]:
                        report_data["keywords"][source_name] = result["data"]
                        report_data["metadata"]["sources_succeeded"].append(source_name)
                        logger.info(f"Successfully collected data from {source_name}")
                    else:
                        report_data["metadata"]["sources_failed"].append(source_name)
                        report_data["metadata"]["errors"][source_name] = result.get("error", "Unknown error")
                        logger.error(f"Failed to collect from {source_name}: {result.get('error')}")

                except Exception as e:
                    logger.error(f"Error with collector {source_name}: {str(e)}")
                    report_data["metadata"]["sources_failed"].append(source_name)
                    report_data["metadata"]["errors"][source_name] = str(e)

                finally:
                    # Update progress
                    completed_collectors += 1
                    progress = int((completed_collectors / total_collectors) * 100)
                    report_data["metadata"]["progress"] = progress

                    # Save intermediate results
                    report.data = json.dumps(report_data)
                    db.session.commit()

            # Mark as complete if at least one source succeeded
            if len(report_data["metadata"]["sources_succeeded"]) > 0:
                report.status = "complete"
                report.generated_at = datetime.utcnow()
                logger.info(f"Report {report_id} completed successfully with {len(report_data['metadata']['sources_succeeded'])} sources")
            else:
                report.status = "failed"
                logger.error(f"Report {report_id} failed - no sources succeeded")

            report.data = json.dumps(report_data)
            db.session.commit()

            return {
                "report_id": report_id,
                "status": report.status,
                "sources_succeeded": len(report_data["metadata"]["sources_succeeded"]),
                "sources_failed": len(report_data["metadata"]["sources_failed"])
            }

        except Exception as e:
            logger.error(f"Fatal error generating report {report_id}: {str(e)}")
            report = Report.query.get(report_id)
            if report:
                report.status = "failed"
                db.session.commit()
            return {"error": str(e)}
