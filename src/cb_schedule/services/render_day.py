#!/usr/bin/env python3
"""
Render a specific day's ferry schedule as HTML using Jinja2 templates.
"""

import argparse
import sys
import traceback
import shutil
from datetime import datetime, date
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

def load_schedule(schedule_path: Path):
    """Load ferry schedule data from YAML file."""
    if not schedule_path.exists():
        raise FileNotFoundError(f"Schedule file not found: {schedule_path}")
    
    with open(schedule_path, 'r') as f:
        return yaml.safe_load(f)

def get_day_abbreviation(target_date: date):
    """Convert date to day abbreviation (MO, TU, etc.)."""
    day_map = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
    return day_map[target_date.weekday()]

def format_time(time_str: str, use_12h: bool = False):
    """Format time string to 12H or 24H format."""
    if not time_str:
        return time_str
    
    if not use_12h:
        return time_str
    
    try:
        # Parse 24H format and convert to 12H
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        return time_obj.strftime("%I:%M %p").lstrip('0')
    except ValueError:
        # If parsing fails, return original
        return time_str

def find_active_schedule(schedules: list, target_date: date):
    """Find the active schedule for the target date."""
    for schedule in schedules:
        start_date = schedule.get('start')
        end_date = schedule.get('end')
        
        if start_date and start_date <= target_date:
            if not end_date or target_date <= end_date:
                return schedule
    return None

def get_ferries_for_day(schedule_data: dict, target_date: date, use_12h: bool = False):
    """Get all ferries running on the target date from all services."""
    day_abbrev = get_day_abbreviation(target_date)
    all_ferries = []
    services_info = []
    primary_timezone = None
    
    services = schedule_data.get('services', {})
    
    for service_name, service_data in services.items():
        # Use first service's timezone as primary
        if primary_timezone is None:
            primary_timezone = service_data.get('tzid', 'UTC')
        
        schedules = service_data.get('schedules', [])
        active_schedule = find_active_schedule(schedules, target_date)
        # Collect service info for links
        services_info.append({
            'name': f"{service_name.upper()} {active_schedule['name']}" if active_schedule else service_name,
            'url': active_schedule.get('url', '#') if active_schedule else service_data.get("url", "#")
        })
        
        if active_schedule:
            service_url = active_schedule.get('url', '#')
            ferries = active_schedule.get('ferries', [])
            for ferry in ferries:
                byday = ferry.get('byday', [])
                if day_abbrev in byday:
                    original_time = ferry.get('time')
                    ferry_info = {
                        'service': service_name,
                        'service_url': service_url,
                        'time': format_time(original_time, use_12h),
                        'original_time': original_time,  # Keep for sorting
                        'start_location': ferry.get('from', None),
                        'end_location': ferry.get('to', None)
                    }
                    all_ferries.append(ferry_info)
    
    # Sort ferries by original 24H time
    all_ferries.sort(key=lambda x: x.get('original_time', '00:00'))
    return all_ferries, services_info, primary_timezone

def render_day_html(target_date: date, ferries: list, services: list, timezone: str, template_dir: Path, output_path: Path, show_direction_colors: bool = True):
    """Render the day's schedule as HTML."""
    
    # Set up Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )
    
    # Load template
    template = env.get_template('day.html')
    
    # Prepare template data
    template_data = {
        'date': target_date,
        'date_formatted': target_date.strftime('%A, %B %d, %Y'),
        'ferries': ferries,
        'services': services,
        'timezone': timezone,
        'day_name': target_date.strftime('%A'),
        'generation_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'show_direction_colors': show_direction_colors
    }
    
    # Render HTML
    html_content = template.render(**template_data)
    
    # Write to file
    with open(output_path, 'w') as f:
        f.write(html_content)

def parse_args():
    parser = argparse.ArgumentParser(description="Render daily ferry schedule as HTML")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--schedule", default="schedule.yaml", help="Path to schedule YAML file")
    parser.add_argument("--template-dir", default="templates", help="Directory containing Jinja2 templates")
    parser.add_argument("--output", required=True, help="Output HTML file path")
    parser.add_argument("--12h", action="store_true", help="Display times in 12-hour format instead of 24-hour")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Parse target date
    try:
        target_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"ERROR: Invalid date format: {args.date}. Use YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    
    # Load schedule data
    try:
        schedule_data = load_schedule(Path(args.schedule))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Get ferries for the day
    ferries, services, timezone = get_ferries_for_day(schedule_data, target_date, getattr(args, '12h', False))
    
    # Render HTML
    template_dir = Path(args.template_dir)
    output_path = Path(args.output)
    
    render_day_html(target_date, ferries, services, timezone, template_dir, output_path)
    print(f"Generated HTML for {target_date} -> {output_path}")

if __name__ == "__main__":
    main()