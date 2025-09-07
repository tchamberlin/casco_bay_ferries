#!/usr/bin/env python3
"""
Publish a static ferry schedule site with HTML pages for multiple days.
"""

import argparse
import shutil
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
import yaml
from cb_schedule.services.render_day import get_ferries_for_day, render_day_html, load_schedule

def copy_static_files(template_dir: Path, output_dir: Path):
    """Copy CSS and other static files to output directory."""
    css_source = template_dir / "styles.css"
    if css_source.exists():
        css_dest = output_dir / "styles.css"
        shutil.copy2(css_source, css_dest)
        print(f"Copied CSS: {css_dest}")
    else:
        print(f"Warning: CSS file not found at {css_source}")

def generate_index_html(output_dir: Path, date_range: list, title: str = "Ferry Schedule"):
    """Generate a simple index.html with links to all days."""
    index_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <header class="page-header">
        <h1>{title}</h1>
        <p>Select a date to view ferry schedules</p>
    </header>
    
    <main class="schedule-container">
        <div class="date-grid">
            {"".join(f'<a href="{d.isoformat()}.html" class="date-link">{d.strftime("%a %b %d")}</a>' for d in date_range)}
        </div>
    </main>
    
    <footer class="page-footer">
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </footer>
</body>
</html>"""
    
    index_path = output_dir / "index.html"
    with open(index_path, 'w') as f:
        f.write(index_content)
    print(f"Generated index: {index_path}")

def filter_ferries_by_direction(ferries, direction):
    """Filter ferries by arrival/departure direction."""
    if direction == "arrive":
        return [f for f in ferries if f.get('end_location') == 'Chebeague Island']
    elif direction == "depart":
        return [f for f in ferries if f.get('start_location') == 'Chebeague Island']
    else:
        return ferries

def generate_filtered_pages(schedule_path, template_dir, output_dir, start_date, days=30, use_12h=False):
    """Generate filtered pages for a date range."""
    
    # Generate arrive/ and depart/ subdirectories
    arrive_dir = output_dir / "arrive"
    depart_dir = output_dir / "depart" 
    arrive_dir.mkdir(exist_ok=True)
    depart_dir.mkdir(exist_ok=True)
    
    # Load schedule data once
    schedule_data = load_schedule(schedule_path)
    
    # Generate pages for each date
    current_date = start_date
    for i in range(days):
        # Get all ferries for this day
        all_ferries, services, timezone = get_ferries_for_day(schedule_data, current_date, use_12h)
        
        # Generate arrival page
        arrive_ferries = filter_ferries_by_direction(all_ferries, "arrive")
        arrive_filename = f"{current_date.isoformat()}.html"
        arrive_path = arrive_dir / arrive_filename
        render_day_html(current_date, arrive_ferries, services, timezone, template_dir, arrive_path, show_direction_colors=False)
        print(f"Generated arrivals: {arrive_path} ({len(arrive_ferries)} ferries)")
        
        # Generate departure page
        depart_ferries = filter_ferries_by_direction(all_ferries, "depart")
        depart_filename = f"{current_date.isoformat()}.html"
        depart_path = depart_dir / depart_filename
        render_day_html(current_date, depart_ferries, services, timezone, template_dir, depart_path, show_direction_colors=False)
        print(f"Generated departures: {depart_path} ({len(depart_ferries)} ferries)")
        
        current_date += timedelta(days=1)

def publish_site(schedule_path: Path, template_dir: Path, output_dir: Path, 
                 start_date: date, days: int = 30, use_12h: bool = False):
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
        
        # Generate HTML for this day
        output_file = output_dir / f"{current_date.isoformat()}.html"
        render_day_html(current_date, ferries, services, timezone, template_dir, output_file)
        
        print(f"Generated: {output_file}")
        current_date += timedelta(days=1)
    
    # Generate index page
    generate_index_html(output_dir, date_range, "Chebeague Island Ferry Schedule")
    
    # Generate filtered pages (arrivals/departures)
    print("\nGenerating filtered pages...")
    generate_filtered_pages(schedule_path, template_dir, output_dir, start_date, days, use_12h)
    
    print(f"\nStatic site published to: {output_dir}")
    print(f"  Main pages: {output_dir}/*.html")
    print(f"  Arrivals: {output_dir}/arrive/*.html") 
    print(f"  Departures: {output_dir}/depart/*.html")
    print(f"To serve locally: python -m http.server -d {output_dir}")

def parse_args():
    parser = argparse.ArgumentParser(description="Publish static ferry schedule site")
    parser.add_argument("--schedule", default="schedule.yaml", help="Path to schedule YAML file")
    parser.add_argument("--template-dir", default="templates", help="Directory containing templates")
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
        print(f"ERROR: Invalid date format: {args.start_date}. Use YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    
    # Publish the site
    publish_site(
        schedule_path=Path(args.schedule),
        template_dir=Path(args.template_dir),
        output_dir=Path(args.output_dir),
        start_date=start_date,
        days=args.days,
        use_12h=getattr(args, '12h', False)
    )

if __name__ == "__main__":
    main()