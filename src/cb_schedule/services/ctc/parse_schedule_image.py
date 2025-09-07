"""
Print the raw table from the image as CSV with 24H time and True/False values.
"""
import logging

import argparse
import sys
import csv
from datetime import datetime
from pathlib import Path
from img2table.document import Image
from img2table.ocr import PaddleOCR

logger = logging.getLogger(__name__)

def parse_time_to_24h(time_str):
    """Parse time string like '8:15PM' and convert to 24H format."""
    if not time_str or not time_str.strip():
        raise ValueError()
    
    # Clean up the time string
    time_str = time_str.strip().replace('\n', ' ').replace(' ', '')
    
    # Parse 12-hour format and convert to 24-hour
    dt = datetime.strptime(time_str, "%I:%M%p")
    return dt.strftime("%H:%M")

def is_service_available(cell_content):
    """Check if cell content indicates service is available (True) or not (False)."""
    if not cell_content:
        return False
    
    content = str(cell_content).strip().lower()
    
    # "No Service" or similar indicates False
    if 'no service' in content:
        return False
    
    # Checkmark symbols indicate True
    checkmarks = ['✓', '√', 'v', '>', '<', '→']
    if content in [c.lower() for c in checkmarks]:
        return True
    
    raise ValueError(f"Failed to parse {cell_content}")

def parse_schedule_image(image_path: Path):
    """Extract table and output as CSV with 24H time and True/False values."""
    
    # Initialize OCR
    ocr = PaddleOCR(lang="en")
    
    image = Image(src=str(image_path))
    
    extracted_tables = image.extract_tables(
        ocr=ocr,
        implicit_rows=False,
        borderless_tables=False
    )
    
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
            elif hasattr(cell, 'value'):
                row_values.append(cell.value if cell.value else "")
            elif isinstance(cell, str):
                row_values.append(cell)
            else:
                row_values.append(str(cell))
        rows.append(row_values)

    return rows
    
def write_csv(table: list[list], output_path: Path|None = None):

    if not table:
        raise ValueError("No data found in table")
    
    if output_path:
        output_file = open(output_path, 'w', newline='')
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
    parser = argparse.ArgumentParser(description="Extract ferry schedule and output as CSV with 24H time and True/False values")
    parser.add_argument("--image", required=True, help="Path to schedule image file")
    parser.add_argument("--output", help="Path to save CSV file (defaults to stdout)")
    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: Image file not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else None
    convert_schedule_image_to_csv(image_path, output_path)

if __name__ == "__main__":
    main()