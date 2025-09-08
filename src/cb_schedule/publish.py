#!/usr/bin/env python3
"""
Publish a static ferry schedule site with HTML pages for multiple days.
"""

import argparse
import shutil
import sys
import logging
from datetime import date, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from cb_schedule.render_day import get_ferries_for_day, render_day_html, load_schedule

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def copy_static_files(template_dir: Path, output_dir: Path):
    """Copy CSS and other static files to output directory."""
    css_source = template_dir / "styles.css"
    if css_source.exists():
        css_dest = output_dir / "styles.css"
        shutil.copy2(css_source, css_dest)
        logger.info(f"Copied CSS: {css_dest}")
    else:
        logger.warning(f"CSS file not found at {css_source}")


def generate_index_html(template_dir: Path, output_dir: Path, date_range: list, title: str = "Ferry Schedule"):
    """Generate a simple index.html that redirects to today's date."""
    # Set up Jinja2 environment
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape(["html", "xml"]))

    # Load template
    template = env.get_template("home.html")

    # Prepare template data
    template_data = {"title": title, "available_dates": date_range, "fallback_date": date_range[0].isoformat()}

    # Render HTML
    index_content = template.render(**template_data)

    index_path = output_dir / "index.html"
    with open(index_path, "w") as f:
        f.write(index_content)
    logger.info(f"Generated index: {index_path}")


def filter_ferries_by_direction(ferries, direction):
    """Filter ferries by arrival/departure direction."""
    if direction == "arrive":
        return [f for f in ferries if f.get("end_location") == "Chebeague Island"]
    elif direction == "depart":
        return [f for f in ferries if f.get("start_location") == "Chebeague Island"]
    else:
        return ferries


def generate_filtered_pages(schedule_path, template_dir, output_dir, start_date, days=30, use_12h=False):
    """Generate filtered pages for a date range with structure /<date>/{arrive,depart}/"""

    # Load schedule data once
    schedule_data = load_schedule(schedule_path)

    # Generate pages for each date
    current_date = start_date
    for i in range(days):
        # Create date directory
        date_dir = output_dir / current_date.isoformat()
        date_dir.mkdir(exist_ok=True)

        # Create arrive/ and depart/ subdirectories under date
        arrive_dir = date_dir / "arrive"
        depart_dir = date_dir / "depart"
        arrive_dir.mkdir(exist_ok=True)
        depart_dir.mkdir(exist_ok=True)

        # Get all ferries for this day
        all_ferries, services, timezone = get_ferries_for_day(schedule_data, current_date, use_12h)

        # Generate arrival page
        arrive_ferries = filter_ferries_by_direction(all_ferries, "arrive")
        arrive_path = arrive_dir / "index.html"
        render_day_html(
            current_date, arrive_ferries, services, timezone, template_dir, arrive_path, show_direction_colors=False
        )
        logger.debug(f"Generated arrivals: {arrive_path} ({len(arrive_ferries)} ferries)")

        # Generate departure page
        depart_ferries = filter_ferries_by_direction(all_ferries, "depart")
        depart_path = depart_dir / "index.html"
        render_day_html(
            current_date, depart_ferries, services, timezone, template_dir, depart_path, show_direction_colors=False
        )
        logger.debug(f"Generated departures: {depart_path} ({len(depart_ferries)} ferries)")

        current_date += timedelta(days=1)


def publish_site(
    schedule_path: Path, template_dir: Path, output_dir: Path, start_date: date, days: int = 30, use_12h: bool = False
):
    """Publish a complete static site with multiple day pages."""

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load schedule data
    schedule_data = load_schedule(schedule_path)

    # Copy static files
    copy_static_files(template_dir, output_dir)

    # Generate pages for date range
    date_range = []
    current_date = start_date

    for i in range(days):
        date_range.append(current_date)

        # Get ferries for this day
        ferries, services, timezone = get_ferries_for_day(schedule_data, current_date, use_12h)

        # Create date directory and generate main day page
        date_dir = output_dir / current_date.isoformat()
        date_dir.mkdir(exist_ok=True)
        output_file = date_dir / "index.html"
        render_day_html(current_date, ferries, services, timezone, template_dir, output_file)

        logger.debug(f"Generated: {output_file}")
        current_date += timedelta(days=1)

    # Generate index page
    generate_index_html(template_dir, output_dir, date_range, "Chebeague Island Ferry Schedule")

    # Generate filtered pages (arrivals/departures)
    logger.info("Generating filtered pages...")
    generate_filtered_pages(schedule_path, template_dir, output_dir, start_date, days, use_12h)

    logger.info(f"Static site published to: {output_dir}")
    logger.info(f"  Main pages: {output_dir}/*/index.html")
    logger.info(f"  Arrivals: {output_dir}/*/arrive/index.html")
    logger.info(f"  Departures: {output_dir}/*/depart/index.html")
    logger.info(f"To serve locally: python -m http.server -d {output_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Publish static ferry schedule site")
    parser.add_argument("--schedule", default="schedule.yaml", help="Path to schedule YAML file")
    parser.add_argument("--template-dir", default="src/cb_schedule/templates", help="Directory containing templates")
    parser.add_argument("--output-dir", default="site", help="Output directory for static site")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to generate (default: 30)")
    parser.add_argument("--12h", action="store_true", help="Use 12-hour time format")
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse start date
    try:
        start_date = date.fromisoformat(args.start_date)
    except ValueError:
        logger.error(f"Invalid date format: {args.start_date}. Use YYYY-MM-DD")
        sys.exit(1)

    # Publish the site
    publish_site(
        schedule_path=Path(args.schedule),
        template_dir=Path(args.template_dir),
        output_dir=Path(args.output_dir),
        start_date=start_date,
        days=args.days,
        use_12h=getattr(args, "12h", False),
    )


if __name__ == "__main__":
    main()
