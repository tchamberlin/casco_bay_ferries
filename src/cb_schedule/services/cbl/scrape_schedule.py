"""
Scrape Casco Bay Lines ferry schedule and convert to YAML format.
"""
import logging
import argparse
import sys
import re
from datetime import datetime, date
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
import yaml
from dateutil import parser as dateparse


logger = logging.getLogger(__name__)

def get_sched(url:str):
    response = httpx.get(url)
    response.raise_for_status()
    return response.text

def parse_cbl_schedule(url:str, html:str):
    """Scrape the Chebeague Island summer schedule from Casco Bay Lines website."""
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the schedule table
    table = soup.find('table')
    if not table:
        raise ValueError("No table found on the page")


    rows = table.find_all("tr")[2:]

    is_am = True
    ferries = []
    for row in rows:
        am_pm = row.find("td", class_="column-1")
        if am_pm and am_pm.get_text().strip().lower() == "pm":
            is_am = False

        leave_portland_time, leave_portland_days = parse_time_to_24h(row.find("td", class_="column-2").get_text(), is_pm=not is_am)
        ferries.append({
            "from": "Portland",
            "to": "Chebeague Island",
            "time": leave_portland_time,
            "days": leave_portland_days,
            }
        )
        leave_chebeague_time, leave_chebeague_days = parse_time_to_24h(row.find("td", class_="column-3").get_text(), is_pm=not is_am)
        ferries.append({
            "from": "Chebeague Island",
            "to": "Portland",
            "time": leave_chebeague_time,
            "days": leave_chebeague_days
            }
        )
    start, end = parse_effective_dates(soup)
    return {
        "start": start, "end": end, "name": url.rstrip("/").split("/")[-1].title(),
        "ferries": ferries, "url": url}

def parse_effective_dates(soup):
    # Find the "Effective:" label
    eff = soup.find("strong", string=re.compile(r"^\s*Effective", re.I))
    if eff is None:
        raise ValueError("Could not find an 'Effective:' label.")

    # Gather text after the label up to a <br> or end of container
    parts = []
    for sib in eff.next_siblings:
        if getattr(sib, "name", None) == "br":
            break
        parts.append(str(sib))
    range_text = BeautifulSoup("".join(parts), "html.parser").get_text(" ", strip=True)

    # Normalize any dash variant to a single hyphen
    range_text = re.sub(r"[\u2012\u2013\u2014\u2015-]+", "-", range_text)

    # Split into start/end
    m = re.search(r"(.+?)\s*-\s*(.+)$", range_text)
    if not m:
        raise ValueError(f"Could not parse date range: {range_text!r}")


    start = dateparse.parse(m.group(1)).date()
    end   = dateparse.parse(m.group(2)).date()
    return start, end
    

def parse_time_to_24h(time_str, is_pm=False):
    """Parse time string and convert to 24H format."""
    if not time_str or not time_str.strip():
        raise ValueError("Empty time string")
    
    all_days = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']

    if time_str.endswith("XF"):
        days = [d for d in all_days if d != "FR"]
    elif time_str.endswith("XF"):
        days = ["FR"]
    else:
        days = all_days
    time_str = time_str.strip().split(" ")[0]
    
    if ':' not in time_str:
        raise ValueError(f"Invalid time format: {time_str}")
    
    try:
        hour_str, minute_str = time_str.split(':')
        hour = int(hour_str)
        minute = int(minute_str)
        
        # Handle 12-hour to 24-hour conversion based on context
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0  # 12:xx AM becomes 00:xx
        
        # Validate time components
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid time values: {hour}:{minute}")
        
        return f"{hour:02d}:{minute:02d}", days
    
    except (ValueError, IndexError) as e:
        raise ValueError(f"Could not parse time '{time_str}': {e}") from e

def convert_to_yaml_schedule(url, schedule_data, schedule_path: Path = Path("schedule.yaml")):
    """Convert scraped schedule data to YAML format matching the existing structure."""
    
    # Load existing YAML
    if schedule_path.exists():
        with open(schedule_path, 'r') as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    
    # Ensure services.cbl structure exists
    if 'services' not in data:
        data['services'] = {}
    if 'cbl' not in data['services']:
        data['services']['cbl'] = {
            'tzid': 'America/New_York',
            'schedules': []
        }
    if 'schedules' not in data['services']['cbl']:
        data['services']['cbl']['schedules'] = []
    
    # Create new schedule entry
    new_schedule = {
        'start': schedule_data['start'],
        'end': schedule_data['end'],
        'name': schedule_data['name'],
        'url': url,

        'ferries': []
    }
    
    
    # Process all ferry departures
    for ferry in schedule_data['ferries']:
        ferry_entry = {
            'time': ferry['time'],
            'from': ferry['from'],
            'to': ferry['to'],
            'byday': ferry["days"]
        }
        new_schedule['ferries'].append(ferry_entry)
    
    # Remove existing schedule with same start date for cbl
    data['services']['cbl']['schedules'] = [s for s in data['services']['cbl']['schedules'] if s.get('start') != schedule_data['start']]
    
    # Add new schedule
    data['services']['cbl']['schedules'].append(new_schedule)
    
    # Sort schedules by start date
    data['services']['cbl']['schedules'].sort(key=lambda x: x.get('start', date.min))
    
    # Write back to file
    with open(schedule_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Casco Bay Lines ferry schedule and convert to YAML")
    parser.add_argument("url")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--output", help="Path to save YAML file (defaults to schedule.yaml)")
    return parser.parse_args()

def main():
    args = parse_args()
    
    if args.path and args.path.exists():
        html = args.path.read_text()
    else:
        html = get_sched(args.url)
        args.path.write_text(html)
    schedule_data = parse_cbl_schedule(args.url, html)
    output_path = Path(args.output) if args.output else Path("schedule.yaml")
    convert_to_yaml_schedule(args.url, schedule_data, output_path)
    print(f"Successfully scraped and saved schedule to {output_path}")
    print(f"Schedule covers {schedule_data['start']} to {schedule_data['end']}")

if __name__ == "__main__":
    main()