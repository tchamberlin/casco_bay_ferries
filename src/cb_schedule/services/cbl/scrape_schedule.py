"""
Scrape Casco Bay Lines ferry schedule and convert to YAML format.
"""

import argparse
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx
from selectolax.parser import HTMLParser
import yaml
from dateutil import parser as dateparse

# Configure logger
from cb_schedule.logging_config import setup_logger

logger = setup_logger(__name__)


def get_sched(url: str) -> str:
    response = httpx.get(url)
    response.raise_for_status()
    return response.text


def parse_cbl_schedule(url: str, html: str) -> Dict[str, Any]:
    """Scrape the Chebeague Island summer schedule from Casco Bay Lines website."""

    parser = HTMLParser(html)

    # Find the schedule table
    table = parser.css_first("table")
    if not table:
        raise ValueError("No table found on the page")

    rows = table.css("tr")[2:]

    is_am = True
    ferries = []
    for row in rows:
        am_pm = row.css_first("td.column-1")
        if am_pm and am_pm.text().strip().lower() == "pm":
            is_am = False

        portland_cell = row.css_first("td.column-2")
        if not portland_cell:
            continue
        leave_portland_time, leave_portland_days = parse_time_to_24h(portland_cell.text(), is_pm=not is_am)
        ferries.append(
            {
                "from": "Portland",
                "to": "Chebeague Island",
                "time": leave_portland_time,
                "days": leave_portland_days,
            }
        )
        chebeague_cell = row.css_first("td.column-3")
        if not chebeague_cell:
            continue
        leave_chebeague_time, leave_chebeague_days = parse_time_to_24h(chebeague_cell.text(), is_pm=not is_am)
        ferries.append(
            {"from": "Chebeague Island", "to": "Portland", "time": leave_chebeague_time, "days": leave_chebeague_days}
        )
    start, end = parse_effective_dates(parser)
    return {"start": start, "end": end, "name": url.rstrip("/").split("/")[-1].title(), "ferries": ferries, "url": url}


def correct_malformed_year(parsed_date: date, reference_date: date | None = None, raw_text: str = "") -> date:
    """
    Correct malformed years in parsed dates.

    Args:
        parsed_date: The date parsed by dateutil
        reference_date: A reference date (e.g., start date) to infer correct year from
        raw_text: The raw text that was parsed, for context

    Returns:
        Corrected date with proper year

    Raises:
        ValueError: If the date cannot be corrected and remains invalid
    """
    current_year = date.today().year

    # If year seems reasonable (within ~50 years of current year), keep it
    if abs(parsed_date.year - current_year) <= 50:
        return parsed_date

    # If we have a reference date and the parsed year is clearly wrong, use the reference year
    if reference_date:
        try:
            corrected = parsed_date.replace(year=reference_date.year)
            logger.info(
                f"Corrected malformed year using reference: '{raw_text}' -> {corrected} (reference year: {reference_date.year})"
            )

            # Validate that corrected date makes sense (end >= start)
            if corrected >= reference_date:
                return corrected
            else:
                raise ValueError(f"Corrected end date {corrected} is before start date {reference_date}")

        except ValueError as e:
            logger.error(f"Could not correct malformed date '{raw_text}': {e}")
            raise ValueError(f"Could not correct malformed date '{raw_text}': {e}")

    # No reference date available and year is invalid
    raise ValueError(
        f"Invalid year in date '{raw_text}' -> {parsed_date} and no reference date available for correction"
    )


def parse_effective_dates(parser: HTMLParser) -> Tuple[date, date]:
    # Find the "Effective:" label - look for strong tags and check their text
    strong_tags = parser.css("strong")
    eff = None
    for strong in strong_tags:
        if re.match(r"^\s*Effective", strong.text(), re.I):
            eff = strong
            break

    if eff is None:
        raise ValueError("Could not find an 'Effective:' label.")

    # Get the parent element and extract text after the strong tag
    parent = eff.parent
    if not parent:
        raise ValueError("Could not find parent of Effective label.")

    # Get all text from the parent and extract the date range
    full_text = parent.text(strip=True)
    # Remove the "Effective:" part and get what follows
    effective_match = re.search(r"Effective:?\s*(.+)", full_text, re.I)
    if not effective_match:
        raise ValueError(f"Could not extract date range from: {full_text}")

    range_text = effective_match.group(1).strip()

    # Normalize any dash variant to a single hyphen
    range_text = re.sub(r"[\u2012\u2013\u2014\u2015-]+", "-", range_text)

    # Split into start/end
    m = re.search(r"(.+?)\s*-\s*(.+)$", range_text)
    if not m:
        raise ValueError(f"Could not parse date range: {range_text!r}")

    start_text = m.group(1).strip()
    end_text = m.group(2).strip()

    # Parse the dates
    start = dateparse.parse(start_text).date()
    end = dateparse.parse(end_text).date()

    # Correct any malformed years
    start = correct_malformed_year(start, raw_text=start_text)
    end = correct_malformed_year(end, reference_date=start, raw_text=end_text)

    return start, end


def parse_time_to_24h(time_str: Optional[str], is_pm: bool = False) -> Tuple[str, List[str]]:
    """Parse time string and convert to 24H format."""
    if not time_str or not time_str.strip():
        raise ValueError("Empty time string")

    all_days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    if time_str.endswith("XF"):
        days = [d for d in all_days if d != "FR"]
    elif time_str.endswith("XF"):
        days = ["FR"]
    else:
        days = all_days
    time_str = time_str.strip().split(" ")[0]

    if ":" not in time_str:
        raise ValueError(f"Invalid time format: {time_str}")

    try:
        hour_str, minute_str = time_str.split(":")
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


def convert_to_yaml_schedule(
    url: str, schedule_data: Dict[str, Any], schedule_path: Path = Path("schedule.yaml")
) -> None:
    """Convert scraped schedule data to YAML format matching the existing structure."""

    # Load existing YAML
    if schedule_path.exists():
        with open(schedule_path, "r") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Ensure services.cbl structure exists
    if "services" not in data:
        data["services"] = {}
    if "cbl" not in data["services"]:
        data["services"]["cbl"] = {"tzid": "America/New_York", "schedules": []}
    if "schedules" not in data["services"]["cbl"]:
        data["services"]["cbl"]["schedules"] = []

    # Create new schedule entry
    new_schedule = {
        "start": schedule_data["start"],
        "end": schedule_data["end"],
        "name": schedule_data["name"],
        "url": url,
        "ferries": [],
    }

    # Process all ferry departures
    for ferry in schedule_data["ferries"]:
        ferry_entry = {"time": ferry["time"], "from": ferry["from"], "to": ferry["to"], "byday": ferry["days"]}
        new_schedule["ferries"].append(ferry_entry)

    # Remove existing schedule with same start date for cbl
    data["services"]["cbl"]["schedules"] = [
        s for s in data["services"]["cbl"]["schedules"] if s.get("start") != schedule_data["start"]
    ]

    # Add new schedule
    data["services"]["cbl"]["schedules"].append(new_schedule)

    # Sort schedules by start date
    data["services"]["cbl"]["schedules"].sort(key=lambda x: x.get("start", date.min))

    # Write back to file
    with open(schedule_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Casco Bay Lines ferry schedule and convert to YAML")
    parser.add_argument("url")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--output", help="Path to save YAML file (defaults to schedule.yaml)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.path and args.path.exists():
        html = args.path.read_text()
    else:
        html = get_sched(args.url)
        args.path.write_text(html)
    schedule_data = parse_cbl_schedule(args.url, html)
    output_path = Path(args.output) if args.output else Path("schedule.yaml")
    convert_to_yaml_schedule(args.url, schedule_data, output_path)
    logger.info(f"Successfully scraped and saved schedule to {output_path}")
    logger.info(f"Schedule covers {schedule_data['start']} to {schedule_data['end']}")


if __name__ == "__main__":
    main()
