"""
Extract ferry schedule from image using OCR and convert to YAML format.
"""

import argparse
import sys
import csv
from datetime import datetime, date
from pathlib import Path
from typing import Any, List, Optional
from img2table.document import Image
from img2table.ocr import PaddleOCR
import yaml

# Configure logger
from cb_schedule.logging_config import setup_logger

logger = setup_logger(__name__)


def parse_time_to_24h(time_str: str) -> str:
    """Parse time string like '8:15PM' and convert to 24H format."""
    if not time_str or not time_str.strip():
        raise ValueError("Empty time string")

    # Clean up the time string
    time_str = time_str.strip().replace("\n", " ").replace(" ", "").upper()

    # Handle special case: NOON
    if time_str == "NOON":
        return "12:00"

    # Check if it's already in 24-hour format (HH:MM)
    if ":" in time_str and not any(c in time_str for c in ["AM", "PM"]):
        try:
            # Validate it's a valid time
            datetime.strptime(time_str, "%H:%M")
            return time_str
        except ValueError:
            pass

    # Parse 12-hour format and convert to 24-hour
    try:
        dt = datetime.strptime(time_str, "%I:%M%p")
        return dt.strftime("%H:%M")
    except ValueError as e:
        raise ValueError(f"Could not parse time '{time_str}': {e}")


def is_service_available(cell_content: Any) -> bool:
    """Check if cell content indicates service is available (True) or not (False)."""
    if not cell_content or not str(cell_content).strip():
        return False

    content = str(cell_content).strip().lower()

    # Handle boolean strings
    if content == "true":
        return True
    if content == "false":
        return False

    # "No Service" or similar indicates False
    if "no service" in content:
        return False

    # Checkmark symbols indicate True
    checkmarks = ["✓", "√", "v", ">", "<", "→"]
    if content in [c.lower() for c in checkmarks]:
        return True

    raise ValueError(f"Failed to parse {cell_content}")


def parse_schedule_image(image_path: Path) -> List[List[str]]:
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
    table: List[List[str]],
    name: str,
    start_date: date,
    end_date: Optional[date] = None,
    schedule_path: Path = Path("schedule.yaml"),
) -> None:
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
                "byday": service_days.copy(),
            }
            new_schedule["ferries"].append(leave_chebeague)
            logger.info(f"Added ferry: {leave_chebeague} on {service_days}")

            leave_cousins = {
                "time": leave_cousins_time,
                "from": "Cousins Island",
                "to": "Chebeague Island",
                "byday": service_days.copy(),
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


def read_csv(csv_path: Path) -> List[List[str]]:
    """Read CSV file and return table data."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    table = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            table.append(row)

    if not table:
        raise ValueError("CSV file is empty")

    return table


def write_csv(table: List[List[str]], output_path: Optional[Path] = None) -> None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract ferry schedule and output as YAML")
    parser.add_argument("--image", help="Path to schedule image file")
    parser.add_argument("--csv-input", help="Path to CSV file to read schedule data from (skips image parsing)")
    parser.add_argument("--csv-output", help="Path to save CSV file (for caching parsed table data)")
    parser.add_argument("--output", help="Path to save YAML file (defaults to schedule.yaml)")
    parser.add_argument("--start", required=True, help="Start date for schedule (YYYY-MM-DD)")
    parser.add_argument("--name", required=True, help="The name of the schedule, e.g. Summer or Winter")
    parser.add_argument("--end", help="End date for schedule (YYYY-MM-DD)")
    args = parser.parse_args()
    return args


def main() -> None:
    args = parse_args()

    # Validate that either image or csv-input is provided
    if not args.image and not args.csv_input:
        logger.error("Either --image or --csv-input must be provided")
        sys.exit(1)

    if args.image and args.csv_input:
        logger.error("Cannot specify both --image and --csv-input")
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

    # Get table data either from image parsing or CSV input
    if args.csv_input:
        logger.info(f"Reading schedule data from CSV: {args.csv_input}")
        csv_path = Path(args.csv_input)
        table = read_csv(csv_path)
    else:
        image_path = Path(args.image)
        if not image_path.exists():
            logger.error(f"Image file not found: {image_path}")
            sys.exit(1)

        logger.info(f"Parsing schedule image: {image_path}")
        table = parse_schedule_image(image_path)

        # Optionally save CSV for future use
        if args.csv_output:
            logger.info(f"Saving parsed data to CSV: {args.csv_output}")
            write_csv(table, Path(args.csv_output))

    output_path = Path(args.output) if args.output else Path("schedule.yaml")
    write_yaml_schedule(table, args.name, start_date, end_date, output_path)


if __name__ == "__main__":
    main()
