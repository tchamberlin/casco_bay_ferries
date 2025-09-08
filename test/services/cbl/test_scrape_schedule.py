"""
Unit tests for CBL ferry schedule scraping functionality.
"""

import pytest
from datetime import date
from pathlib import Path
from unittest.mock import patch, Mock
from bs4 import BeautifulSoup

from cb_schedule.services.cbl.scrape_schedule import (
    parse_cbl_schedule,
    parse_time_to_24h,
    parse_effective_dates,
    convert_to_yaml_schedule,
    get_sched,
    correct_malformed_year,
)


class TestParseCBLSchedule:
    """Test the main CBL schedule parsing function."""

    @pytest.fixture
    def summer_html(self):
        """Load summer schedule HTML test data."""
        test_data_path = Path(__file__).parent / "data" / "cbl_summer_schedule_2025.html"
        return test_data_path.read_text()

    @pytest.fixture
    def fall_html(self):
        """Load fall schedule HTML test data."""
        test_data_path = Path(__file__).parent / "data" / "cbl_fall_schedule_2025.html"
        return test_data_path.read_text()

    def test_parse_summer_schedule(self, summer_html):
        """Test parsing of summer schedule HTML."""
        url = "https://www.cascobaylines.com/schedules/chebeague-island-schedule/summer/"
        result = parse_cbl_schedule(url, summer_html)

        # Check basic structure
        assert isinstance(result, dict)
        assert "start" in result
        assert "end" in result
        assert "name" in result
        assert "ferries" in result
        assert "url" in result

        # Check date parsing
        assert result["start"] == date(2025, 6, 21)
        assert result["end"] == date(2025, 9, 1)
        assert result["name"] == "Summer"
        assert result["url"] == url

        # Check ferry data structure
        assert isinstance(result["ferries"], list)
        assert len(result["ferries"]) > 0

        # Check ferry entry structure
        ferry = result["ferries"][0]
        assert "from" in ferry
        assert "to" in ferry
        assert "time" in ferry
        assert "days" in ferry

    def test_parse_fall_schedule(self, fall_html):
        """Test parsing of fall schedule HTML."""
        url = "https://www.cascobaylines.com/schedules/chebeague-island-schedule/fall/"
        result = parse_cbl_schedule(url, fall_html)

        assert result["start"] == date(2025, 9, 2)
        # Note: The test HTML has truncated end date "October 13, 202"
        # but our correction logic should fix it to 2025 based on the start date
        assert result["end"] == date(2025, 10, 13)
        assert result["name"] == "Fall"
        assert len(result["ferries"]) > 0

    def test_parse_schedule_no_table(self):
        """Test error handling when no table is found."""
        html = "<html><body><p>No table here</p></body></html>"
        url = "https://example.com"

        with pytest.raises(ValueError, match="No table found on the page"):
            parse_cbl_schedule(url, html)


class TestParseTimeTo24h:
    """Test time parsing and conversion functionality."""

    def test_basic_time_parsing(self):
        """Test basic time string parsing."""
        time, days = parse_time_to_24h("5:00", is_pm=False)
        assert time == "05:00"
        assert days == ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    def test_pm_time_conversion(self):
        """Test PM time conversion."""
        time, days = parse_time_to_24h("3:00", is_pm=True)
        assert time == "15:00"

    def test_noon_conversion(self):
        """Test 12:00 PM conversion."""
        time, days = parse_time_to_24h("12:00", is_pm=True)
        assert time == "12:00"

    def test_midnight_conversion(self):
        """Test 12:00 AM conversion."""
        time, days = parse_time_to_24h("12:00", is_pm=False)
        assert time == "00:00"

    def test_xf_day_parsing(self):
        """Test 'Except Friday' day parsing."""
        time, days = parse_time_to_24h("5:00 XF", is_pm=False)
        assert time == "05:00"
        expected_days = ["MO", "TU", "WE", "TH", "SA", "SU"]
        assert days == expected_days

    def test_empty_time_string(self):
        """Test error handling for empty time string."""
        with pytest.raises(ValueError, match="Empty time string"):
            parse_time_to_24h("", is_pm=False)

        with pytest.raises(ValueError, match="Empty time string"):
            parse_time_to_24h(None, is_pm=False)

    def test_invalid_time_format(self):
        """Test error handling for invalid time format."""
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_time_to_24h("invalid", is_pm=False)

    def test_invalid_time_values(self):
        """Test error handling for invalid time values."""
        with pytest.raises(ValueError, match="Invalid time values"):
            parse_time_to_24h("25:00", is_pm=False)

        with pytest.raises(ValueError, match="Invalid time values"):
            parse_time_to_24h("12:70", is_pm=False)


class TestCorrectMalformedYear:
    """Test year correction functionality."""

    def test_reasonable_year_unchanged(self):
        """Test that reasonable years are left unchanged."""
        test_date = date(2025, 6, 21)
        result = correct_malformed_year(test_date, raw_text="June 21, 2025")
        assert result == test_date

    def test_truncated_year_without_reference_fails(self):
        """Test that truncated years without reference date raise ValueError."""
        malformed_date = date(202, 10, 13)

        with pytest.raises(ValueError, match="Invalid year.*no reference date"):
            correct_malformed_year(malformed_date, raw_text="October 13, 202")

    def test_reference_date_correction(self):
        """Test correction using reference date."""
        reference = date(2025, 6, 21)
        malformed_date = date(202, 10, 13)

        result = correct_malformed_year(malformed_date, reference_date=reference, raw_text="October 13, 202")

        expected = date(2025, 10, 13)
        assert result == expected

    def test_far_future_year_fails_without_reference(self):
        """Test that very far future years fail without reference date."""
        far_future = date(3025, 6, 21)

        with pytest.raises(ValueError, match="Invalid year.*no reference date"):
            correct_malformed_year(far_future, raw_text="June 21, 3025")

    def test_ancient_year_correction(self):
        """Test correction of obviously wrong ancient years."""
        ancient_date = date(25, 10, 13)  # Year 25 AD
        reference = date(2025, 6, 21)

        result = correct_malformed_year(ancient_date, reference_date=reference, raw_text="October 13, 25")

        # Should be corrected to 2025 using reference
        expected = date(2025, 10, 13)
        assert result == expected

    def test_end_before_start_fails(self):
        """Test that correction fails if end date would be before start date."""
        malformed_date = date(202, 6, 1)  # June 1st
        reference = date(2025, 10, 13)  # October 13th start date

        # If we correct to 2025, June 1, 2025 < October 13, 2025 - should fail
        with pytest.raises(ValueError, match="end date.*before start date"):
            correct_malformed_year(malformed_date, reference_date=reference, raw_text="June 1, 202")


class TestParseEffectiveDates:
    """Test effective date range parsing from HTML."""

    def test_standard_date_range_parsing(self):
        """Test parsing of standard date ranges."""
        html = """
        <div>
            <strong>Effective:</strong> June 21, 2025 – September 1, 2025
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        start, end = parse_effective_dates(soup)

        assert start == date(2025, 6, 21)
        assert end == date(2025, 9, 1)

    def test_malformed_end_date_correction(self):
        """Test correction of malformed end dates like the fall schedule."""
        html = """
        <div>
            <strong>Effective:</strong> September 2, 2025 – October 13, 202
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        start, end = parse_effective_dates(soup)

        assert start == date(2025, 9, 2)
        # End date should be corrected to 2025 based on start date
        assert end == date(2025, 10, 13)

    def test_different_dash_variants(self):
        """Test parsing with different dash characters."""
        html = """
        <div>
            <strong>Effective:</strong> June 21, 2025 — September 1, 2025
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        start, end = parse_effective_dates(soup)

        assert start == date(2025, 6, 21)
        assert end == date(2025, 9, 1)

    def test_no_effective_label(self):
        """Test error handling when no 'Effective:' label is found."""
        html = "<div><strong>Other:</strong> Some text</div>"
        soup = BeautifulSoup(html, "html.parser")

        with pytest.raises(ValueError, match="Could not find an 'Effective:' label"):
            parse_effective_dates(soup)

    def test_invalid_date_range_format(self):
        """Test error handling for invalid date range format."""
        html = """
        <div>
            <strong>Effective:</strong> Invalid date range
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")

        with pytest.raises(ValueError, match="Could not parse date range"):
            parse_effective_dates(soup)


class TestGetSched:
    """Test the HTTP schedule fetching functionality."""

    @patch("cb_schedule.services.cbl.scrape_schedule.httpx.get")
    def test_successful_fetch(self, mock_get):
        """Test successful HTTP fetch."""
        mock_response = Mock()
        mock_response.text = "<html>Test content</html>"
        mock_get.return_value = mock_response

        result = get_sched("https://example.com/schedule")

        assert result == "<html>Test content</html>"
        mock_get.assert_called_once_with("https://example.com/schedule")
        mock_response.raise_for_status.assert_called_once()

    @patch("cb_schedule.services.cbl.scrape_schedule.httpx.get")
    def test_http_error(self, mock_get):
        """Test HTTP error handling."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="HTTP Error"):
            get_sched("https://example.com/schedule")


class TestConvertToYamlSchedule:
    """Test YAML schedule conversion functionality."""

    @pytest.fixture
    def sample_schedule_data(self):
        """Sample schedule data for testing."""
        return {
            "start": date(2025, 6, 21),
            "end": date(2025, 9, 1),
            "name": "Summer",
            "ferries": [
                {
                    "from": "Portland",
                    "to": "Chebeague Island",
                    "time": "05:00",
                    "days": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"],
                },
                {
                    "from": "Chebeague Island",
                    "to": "Portland",
                    "time": "06:00",
                    "days": ["MO", "TU", "WE", "TH", "FR", "SA", "SU"],
                },
            ],
            "url": "https://example.com/schedule",
        }

    def test_create_new_yaml_file(self, sample_schedule_data, tmp_path):
        """Test creating a new YAML file."""
        yaml_path = tmp_path / "test_schedule.yaml"
        url = "https://example.com/schedule"

        convert_to_yaml_schedule(url, sample_schedule_data, yaml_path)

        assert yaml_path.exists()

        # Read and verify the YAML structure
        import yaml

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        assert "services" in data
        assert "cbl" in data["services"]
        assert "schedules" in data["services"]["cbl"]
        assert len(data["services"]["cbl"]["schedules"]) == 1

        schedule = data["services"]["cbl"]["schedules"][0]
        assert schedule["name"] == "Summer"
        assert schedule["start"] == date(2025, 6, 21)
        assert schedule["end"] == date(2025, 9, 1)
        assert len(schedule["ferries"]) == 2

    def test_append_to_existing_yaml(self, sample_schedule_data, tmp_path):
        """Test appending to existing YAML file."""
        yaml_path = tmp_path / "existing_schedule.yaml"

        # Create existing YAML structure
        import yaml

        existing_data = {
            "services": {
                "ctc": {"tzid": "America/New_York", "schedules": []},
                "cbl": {
                    "tzid": "America/New_York",
                    "schedules": [
                        {"name": "Spring", "start": date(2025, 3, 1), "end": date(2025, 6, 20), "ferries": []}
                    ],
                },
            }
        }

        with open(yaml_path, "w") as f:
            yaml.dump(existing_data, f)

        # Add new schedule
        url = "https://example.com/summer-schedule"
        convert_to_yaml_schedule(url, sample_schedule_data, yaml_path)

        # Verify both schedules exist
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        assert len(data["services"]["cbl"]["schedules"]) == 2

        # Should be sorted by start date
        schedules = data["services"]["cbl"]["schedules"]
        assert schedules[0]["name"] == "Spring"
        assert schedules[1]["name"] == "Summer"

    def test_replace_existing_schedule_same_start_date(self, sample_schedule_data, tmp_path):
        """Test replacing schedule with same start date."""
        yaml_path = tmp_path / "schedule.yaml"
        url = "https://example.com/schedule"

        # First conversion
        convert_to_yaml_schedule(url, sample_schedule_data, yaml_path)

        # Modify the schedule data
        modified_data = sample_schedule_data.copy()
        modified_data["name"] = "Summer Updated"
        modified_data["ferries"] = modified_data["ferries"][:1]  # Remove one ferry

        # Second conversion with same start date
        convert_to_yaml_schedule(url, modified_data, yaml_path)

        # Verify only one schedule exists with updated data
        import yaml

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        assert len(data["services"]["cbl"]["schedules"]) == 1
        schedule = data["services"]["cbl"]["schedules"][0]
        assert schedule["name"] == "Summer Updated"
        assert len(schedule["ferries"]) == 1


class TestIntegration:
    """Integration tests using real HTML test data."""

    def test_full_parsing_workflow_summer(self):
        """Test complete parsing workflow with summer data."""
        test_data_path = Path(__file__).parent / "data" / "cbl_summer_schedule_2025.html"
        html = test_data_path.read_text()
        url = "https://www.cascobaylines.com/schedules/chebeague-island-schedule/summer/"

        # Parse the schedule
        schedule_data = parse_cbl_schedule(url, html)

        # Verify we got reasonable data
        assert schedule_data["start"] == date(2025, 6, 21)
        assert schedule_data["end"] == date(2025, 9, 1)
        assert len(schedule_data["ferries"]) >= 8  # Should have multiple ferries per day

        # Check that we have both directions
        origins = set(ferry["from"] for ferry in schedule_data["ferries"])
        assert "Portland" in origins
        assert "Chebeague Island" in origins

        # Check time formats
        times = [ferry["time"] for ferry in schedule_data["ferries"]]
        for time_str in times:
            assert ":" in time_str
            hour, minute = time_str.split(":")
            assert 0 <= int(hour) <= 23
            assert 0 <= int(minute) <= 59

    def test_full_parsing_workflow_fall(self):
        """Test complete parsing workflow with fall data."""
        test_data_path = Path(__file__).parent / "data" / "cbl_fall_schedule_2025.html"
        html = test_data_path.read_text()
        url = "https://www.cascobaylines.com/schedules/chebeague-island-schedule/fall/"

        schedule_data = parse_cbl_schedule(url, html)

        # Check basic structure and corrected dates
        assert schedule_data["start"] == date(2025, 9, 2)
        # Note: Test HTML has truncated end date, but correction logic fixes it
        assert schedule_data["end"] == date(2025, 10, 13)
        assert schedule_data["name"] == "Fall"
        assert len(schedule_data["ferries"]) >= 8

        # Check that we have both directions
        origins = set(ferry["from"] for ferry in schedule_data["ferries"])
        assert "Portland" in origins
        assert "Chebeague Island" in origins

        # Check time formats are valid
        times = [ferry["time"] for ferry in schedule_data["ferries"]]
        for time_str in times:
            assert ":" in time_str
            hour, minute = time_str.split(":")
            assert 0 <= int(hour) <= 23
            assert 0 <= int(minute) <= 59

        # Check for day restrictions (XF - Except Friday patterns)
        days_lists = [ferry["days"] for ferry in schedule_data["ferries"]]

        # Verify all day lists are valid
        all_valid_days = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}
        for days in days_lists:
            assert isinstance(days, list)
            assert len(days) > 0  # Should have at least one day
            assert all(day in all_valid_days for day in days)

        # Check for potential XF restrictions (6 days excluding Friday)
        xf_restrictions = [days for days in days_lists if len(days) == 6 and "FR" not in days]

        # Log what we found for debugging
        if xf_restrictions:
            print(f"Found {len(xf_restrictions)} potential XF (Except Friday) restrictions")

        # Ensure we have reasonable ferry coverage
        total_service_days = sum(len(days) for days in days_lists)
        assert total_service_days > 0, "Should have some ferry services scheduled"


if __name__ == "__main__":
    pytest.main([__file__])
