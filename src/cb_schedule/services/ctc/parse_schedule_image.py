"""
Extract ferry schedule from image using OCR and convert to YAML format.
"""

import logging
import argparse
import sys
import csv
from datetime import datetime, date
from pathlib import Path
from img2table.document import Image
from img2table.ocr import PaddleOCR
import yaml

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def parse_time_to_24h(time_str):
    """Parse time string like '8:15PM' and convert to 24H format."""
    if not time_str or not time_str.strip():
        raise ValueError("Empty time string")

    # Clean up the time string
    time_str = time_str.strip().replace("\n", " ").replace(" ", "").upper()

    # Handle special case: NOON
    if time_str == "NOON":
        return "12:00"

    # Parse 12-hour format and convert to 24-hour
    try:
        dt = datetime.strptime(time_str, "%I:%M%p")
        return dt.strftime("%H:%M")
    except ValueError as e:
        raise ValueError(f"Could not parse time '{time_str}': {e}")


def is_service_available(cell_content):
    """Check if cell content indicates service is available (True) or not (False)."""
    if not cell_content:
        return False

    content = str(cell_content).strip().lower()

    # "No Service" or similar indicates False
    if "no service" in content:
        return False

    # Checkmark symbols indicate True
    checkmarks = ["✓", "√", "v", ">", "<", "→"]
    if content in [c.lower() for c in checkmarks]:
        return True

    raise ValueError(f"Failed to parse {cell_content}")


def parse_schedule_image(image_path: Path):
    """Extract table and output as CSV with 24H time and True/False values."""

    # Initialize OCR
    ocr = PaddleOCR(lang="en")

    image = Image(src=str(image_path))

    extracted_tables = image.extract_tables(ocr=ocr, implicit_rows=False, borderless_tables=False)

    if not extracted_tables:
        raise ValueError("No tables found in image")

    if len(extracted_tables) > 1:
        raise ValueError("Detected multiple tables")

    table = extracted_tables[0]

    # Get table data
    rows = []
    for _, row in table.content.items():
        row_values = []
        for cell in row:
            if cell is None:
                row_values.append("")
            elif hasattr(cell, "value"):
                row_values.append(cell.value if cell.value else "")
            elif isinstance(cell, str):
                row_values.append(cell)
            else:
                row_values.append(str(cell))
        rows.append(row_values)

    return rows


def write_yaml_schedule(
    table: list[list],
    name: str,
    start_date: date,
    end_date: date | None = None,
    schedule_path: Path = Path("schedule.yaml"),
):
    """Write ferry schedule data to YAML file."""

    if not table:
        raise ValueError("No data found in table")

    # Load existing YAML
    if schedule_path.exists():
        with open(schedule_path, "r") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Ensure services.ctc structure exists
    if "services" not in data:
        data["services"] = {}
    if "ctc" not in data["services"]:
        data["services"]["ctc"] = {"tzid": "America/New_York", "schedules": []}
    if "schedules" not in data["services"]["ctc"]:
        data["services"]["ctc"]["schedules"] = []

    # Create new schedule entry
    new_schedule = {
        "name": name,
        "url": "https://www.ctcferry.org/#schedule",  # TODO: hardcoded for now....
        "start": start_date,
    }

    # Add end date if provided (right after start)
    if end_date:
        new_schedule["end"] = end_date

    # Add ferries list
    new_schedule["ferries"] = []

    # Days mapping
    day_map = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    # Process each row
    for i, row in enumerate(table[1:], 1):
        if len(row) < 2 or not row[1]:
            continue

        try:
            # Get departure time from second column
            leave_chebeague_time = parse_time_to_24h(row[1])
            leave_cousins_time = parse_time_to_24h(row[2])

            # Get service days from columns 3-9 (7 days)
            service_days = []
            for day_idx, day_abbrev in enumerate(day_map):
                if day_idx + 3 < len(row):
                    try:
                        if is_service_available(row[day_idx + 3]):
                            service_days.append(day_abbrev)
                    except ValueError as service_error:
                        logger.warning(
                            f"Could not parse service availability in row {i}, column {day_idx + 3}: '{row[day_idx + 3]}' - {service_error}"
                        )

            leave_chebeague = {
                "time": leave_chebeague_time,
                "from": "Chebeague Island",
                "to": "Cousins Island",
                "byday": service_days,
            }
            new_schedule["ferries"].append(leave_chebeague)
            logger.info(f"Added ferry: {leave_chebeague} on {service_days}")

            leave_cousins = {
                "time": leave_cousins_time,
                "from": "Cousins Island",
                "to": "Chebeague Island",
                "byday": service_days,
            }
            new_schedule["ferries"].append(leave_cousins)

        except ValueError as e:
            logger.error(f"Skipping row {i} (time: '{row[1] if len(row) > 1 else 'N/A'}'): {e}")
            continue

    # Remove existing schedule with same start date
    data["services"]["ctc"]["schedules"] = [
        s for s in data["services"]["ctc"]["schedules"] if s.get("start") != start_date
    ]

    # Add new schedule
    data["services"]["ctc"]["schedules"].append(new_schedule)

    # Sort schedules by start date
    data["services"]["ctc"]["schedules"].sort(key=lambda x: x.get("start", date.min))

    # Write back to file
    with open(schedule_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def write_csv(table: list[list], output_path: Path | None = None):
    if not table:
        raise ValueError("No data found in table")

    if output_path:
        output_file = open(output_path, "w", newline="")
        writer = csv.writer(output_file)
    else:
        output_file = None
        writer = csv.writer(sys.stdout)

    try:
        ferries = [f.replace("\n", " ") for f in table[0][:3]]
        days = table[0][3:]

        writer.writerow([*ferries, *days])

        for i, row in enumerate(table[1:], 1):
            if len(row) < 2 or not row[1]:
                logger.debug(f"Skipping row {i}")
                continue

            ferry_times = [parse_time_to_24h(v) for v in row[:3]]
            service_available = [is_service_available(v) for v in row[3:]]
            csv_row = [*ferry_times, *service_available]

            writer.writerow(csv_row)
    finally:
        if output_file:
            output_file.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Extract ferry schedule and output as YAML")
    parser.add_argument("--image", required=True, help="Path to schedule image file")
    parser.add_argument("--output", help="Path to save YAML file (defaults to schedule.yaml)")
    parser.add_argument("--start", required=True, help="Start date for schedule (YYYY-MM-DD)")
    parser.add_argument("--name", required=True, help="The name of the schedule, e.g. Summer or Winter")
    parser.add_argument("--end", help="End date for schedule (YYYY-MM-DD)")
    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        logger.error(f"Image file not found: {image_path}")
        sys.exit(1)

    try:
        start_date = date.fromisoformat(args.start)
    except ValueError:
        logger.error(f"Invalid start date format: {args.start}. Use YYYY-MM-DD")
        sys.exit(1)

    end_date = None
    if args.end:
        try:
            end_date = date.fromisoformat(args.end)
        except ValueError:
            logger.error(f"Invalid end date format: {args.end}. Use YYYY-MM-DD")
            sys.exit(1)

    table = parse_schedule_image(image_path)

    output_path = Path(args.output) if args.output else Path("schedule.yaml")
    write_yaml_schedule(table, args.name, start_date, end_date, output_path)


if __name__ == "__main__":
    main()
