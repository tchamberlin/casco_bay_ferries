# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python package for processing ferry schedules for Chebeague Island transportation services. It handles two main ferry services:
- **CTC (Chebeague Transportation Company)**: Processes schedule images using OCR
- **CBL (Casco Bay Lines)**: Scrapes web-based schedules

The system converts various schedule formats into a unified YAML format and generates static HTML pages for public consumption.

## Key Commands

### Development Environment
- **Install dependencies**: `uv install` (includes development dependencies)
- **Run with uv**: All commands should be prefixed with `uv run`

### Core Scripts (Available via project.scripts in pyproject.toml)
- **Process CTC image schedule**: `uv run ctc-schedule --image <path> --start YYYY-MM-DD --name <schedule_name>`
- **Scrape CBL web schedule**: `uv run cbl-schedule <url> [--output schedule.yaml]`
- **Render single day**: `uv run render-day --date YYYY-MM-DD --output <file.html>`
- **Publish static site**: `uv run publish --start-date YYYY-MM-DD --output-dir site --days 30`

### Example Workflow
```bash
# Process a CTC image schedule
uv run ctc-schedule --image CTC_Summer_Schedule.jpg --start 2025-06-01 --name Summer

# Scrape CBL schedule
uv run cbl-schedule https://www.cascobaylines.com/chebeague-island-summer-schedule

# Generate static site for 30 days
uv run publish --start-date 2025-06-01 --days 30
```

## Architecture

### Package Structure
- `src/cb_schedule/services/`
  - `ctc/parse_schedule_image.py`: OCR processing for CTC image-based schedules
  - `cbl/scrape_schedule.py`: Web scraping for CBL HTML schedules
  - `render_day.py`: Renders individual day schedules as HTML
  - `publish.py`: Generates complete static site with multiple pages

### Data Flow
1. **Input Processing**: Raw schedules (images/web) → YAML format
2. **Template Rendering**: YAML + Jinja2 templates → HTML pages
3. **Site Generation**: Multiple HTML pages organized by date with arrive/depart filtering

### Key Dependencies
- **OCR**: PaddleOCR for image text extraction
- **Web Scraping**: httpx + BeautifulSoup for CBL schedules
- **Templating**: Jinja2 for HTML generation
- **Image Processing**: img2table for table extraction from schedule images

### Schedule Data Format
All schedules are normalized to YAML with this structure:
```yaml
services:
  ctc:
    tzid: America/New_York
    schedules:
      - start: 2025-06-01
        end: 2025-09-15
        name: Summer
        ferries:
          - time: "06:30"
            from: Chebeague Island
            to: Cousins Island
            byday: [MO, TU, WE, TH, FR]
```

## Testing and Development

The project uses standard Python tooling managed by uv. Always run commands with `uv run` to ensure proper dependency resolution.

Templates are expected in a `templates/` directory and should include `day.html` and `home.html` for the publish functionality.
