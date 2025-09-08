"""Unit tests for CTC schedule parsing functionality."""

import pytest
import tempfile
import yaml
from datetime import date
from pathlib import Path

from cb_schedule.services.ctc.parse_schedule_image import (
    parse_time_to_24h,
    is_service_available,
    read_csv,
    write_csv,
    write_yaml_schedule,
)


class TestParseTimeTo24h:
    """Test cases for the parse_time_to_24h function."""

    def test_parse_morning_times(self):
        """Test parsing morning times."""
        assert parse_time_to_24h("6:30AM") == "06:30"
        assert parse_time_to_24h("8:15AM") == "08:15"
        assert parse_time_to_24h("10:45AM") == "10:45"
        assert parse_time_to_24h("11:30AM") == "11:30"

    def test_parse_afternoon_times(self):
        """Test parsing afternoon/evening times."""
        assert parse_time_to_24h("12:00PM") == "12:00"
        assert parse_time_to_24h("2:30PM") == "14:30"
        assert parse_time_to_24h("4:15PM") == "16:15"
        assert parse_time_to_24h("6:30PM") == "18:30"
        assert parse_time_to_24h("8:00PM") == "20:00"
        assert parse_time_to_24h("11:45PM") == "23:45"

    def test_parse_noon_special_case(self):
        """Test parsing NOON special case."""
        assert parse_time_to_24h("NOON") == "12:00"
        assert parse_time_to_24h("noon") == "12:00"
        assert parse_time_to_24h("Noon") == "12:00"

    def test_parse_with_spaces_and_newlines(self):
        """Test parsing times with whitespace and newlines."""
        assert parse_time_to_24h(" 8:15PM ") == "20:15"
        assert parse_time_to_24h("8:15PM\n") == "20:15"
        assert parse_time_to_24h(" 8:15 PM ") == "20:15"

    def test_parse_24h_format_times(self):
        """Test parsing times already in 24-hour format."""
        assert parse_time_to_24h("06:30") == "06:30"
        assert parse_time_to_24h("08:00") == "08:00"
        assert parse_time_to_24h("13:45") == "13:45"
        assert parse_time_to_24h("23:59") == "23:59"
        assert parse_time_to_24h(" 14:30 ") == "14:30"

    def test_parse_invalid_times(self):
        """Test parsing invalid time strings."""
        with pytest.raises(ValueError, match="Empty time string"):
            parse_time_to_24h("")

        with pytest.raises(ValueError, match="Empty time string"):
            parse_time_to_24h("   ")

        with pytest.raises(ValueError, match="Could not parse time"):
            parse_time_to_24h("invalid")

        with pytest.raises(ValueError, match="Could not parse time"):
            parse_time_to_24h("25:00PM")


class TestIsServiceAvailable:
    """Test cases for the is_service_available function."""

    def test_checkmark_symbols_return_true(self):
        """Test that checkmark symbols return True."""
        checkmarks = ["✓", "√", "v", "V", ">", "<", "→"]
        for checkmark in checkmarks:
            assert is_service_available(checkmark) is True
            assert is_service_available(f" {checkmark} ") is True  # with spaces

    def test_boolean_strings_return_correct_values(self):
        """Test that 'True'/'False' strings return correct boolean values."""
        assert is_service_available("True") is True
        assert is_service_available("true") is True
        assert is_service_available(" TRUE ") is True
        assert is_service_available("False") is False
        assert is_service_available("false") is False
        assert is_service_available(" FALSE ") is False

    def test_no_service_returns_false(self):
        """Test that 'No Service' variations return False."""
        no_service_variations = [
            "No Service",
            "no service",
            "NO SERVICE",
            "No service",
            " No Service ",
        ]
        for variation in no_service_variations:
            assert is_service_available(variation) is False

    def test_empty_content_returns_false(self):
        """Test that empty content returns False."""
        assert is_service_available("") is False
        assert is_service_available(None) is False
        assert is_service_available("   ") is False

    def test_unrecognized_content_raises_error(self):
        """Test that unrecognized content raises ValueError."""
        with pytest.raises(ValueError, match="Failed to parse"):
            is_service_available("unknown")

        with pytest.raises(ValueError, match="Failed to parse"):
            is_service_available("?")


class TestCsvOperations:
    """Test cases for CSV read/write operations."""

    def test_read_csv_success(self):
        """Test successful CSV reading."""
        # Use the existing test data file
        csv_path = Path("test/services/ctc/data/ctc_summer_schedule.csv")
        if csv_path.exists():
            table = read_csv(csv_path)
            assert len(table) > 0
            assert len(table[0]) == 10  # header row has 10 columns
            assert table[0][0] == "BUS DEPARTS ROUTE 1"

    def test_read_csv_file_not_found(self):
        """Test CSV reading with non-existent file."""
        with pytest.raises(FileNotFoundError, match="CSV file not found"):
            read_csv(Path("nonexistent.csv"))

    def test_write_and_read_csv_roundtrip(self):
        """Test writing CSV and reading it back."""
        test_data = [
            ["BUS DEPARTS ROUTE 1", "DEPARTS CHEBEAGUE", "DEPARTS COUSINS", "MON", "TUES"],
            ["06:15", "06:30", "06:45", "True", "False"],
            ["07:45", "08:00", "08:15", "True", "True"],
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Write CSV
            write_csv(test_data, temp_path)

            # Read it back
            result = read_csv(temp_path)

            assert result == test_data
        finally:
            temp_path.unlink(missing_ok=True)

    def test_read_existing_test_csv(self):
        """Test reading the existing test CSV file."""
        csv_path = Path("test/services/ctc/data/ctc_summer_schedule.csv")
        if csv_path.exists():
            table = read_csv(csv_path)

            # Verify structure
            assert len(table) > 1  # At least header + 1 data row
            assert table[0][0] == "BUS DEPARTS ROUTE 1"
            assert table[0][1] == "DEPARTS CHEBEAGUE"
            assert table[0][2] == "DEPARTS COUSINS"

            # Verify a data row
            if len(table) > 1:
                # First data row should be: 06:15,06:30,06:45,True,True,True,True,True,True,False
                first_row = table[1]
                assert first_row[0] == "06:15"
                assert first_row[1] == "06:30"
                assert first_row[2] == "06:45"
                assert first_row[3] == "True"  # Monday
                assert first_row[9] == "False"  # Sunday

    def test_write_csv_empty_table(self):
        """Test writing empty table raises error."""
        with pytest.raises(ValueError, match="No data found in table"):
            write_csv([])


class TestYamlScheduleWriting:
    """Test cases for YAML schedule writing."""

    def test_write_yaml_schedule_new_file(self):
        """Test writing YAML schedule to new file."""
        test_table = [
            [
                "BUS DEPARTS ROUTE 1",
                "DEPARTS CHEBEAGUE",
                "DEPARTS COUSINS",
                "MON",
                "TUES",
                "WED",
                "THURS",
                "FRI",
                "SAT",
                "SUN",
            ],
            ["06:15", "06:30", "06:45", "True", "True", "True", "True", "True", "True", "False"],
            ["07:45", "08:00", "08:15", "True", "True", "True", "True", "True", "True", "True"],
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_yaml_schedule(test_table, "Test Schedule", date(2025, 6, 1), date(2025, 9, 15), temp_path)

            # Verify the file was created and has expected structure
            with open(temp_path) as f:
                data = yaml.safe_load(f)

            assert "services" in data
            assert "ctc" in data["services"]
            assert "schedules" in data["services"]["ctc"]
            assert len(data["services"]["ctc"]["schedules"]) == 1

            schedule = data["services"]["ctc"]["schedules"][0]
            assert schedule["name"] == "Test Schedule"
            assert schedule["start"] == date(2025, 6, 1)
            assert schedule["end"] == date(2025, 9, 15)
            assert "ferries" in schedule
            assert len(schedule["ferries"]) == 4  # 2 rows × 2 directions

        finally:
            temp_path.unlink(missing_ok=True)

    def test_write_yaml_schedule_append_to_existing(self):
        """Test appending schedule to existing YAML file."""
        # Create initial YAML content
        initial_data = {
            "services": {
                "ctc": {
                    "tzid": "America/New_York",
                    "schedules": [{"name": "Existing Schedule", "start": date(2025, 3, 1), "ferries": []}],
                }
            }
        }

        test_table = [
            [
                "BUS DEPARTS ROUTE 1",
                "DEPARTS CHEBEAGUE",
                "DEPARTS COUSINS",
                "MON",
                "TUES",
                "WED",
                "THURS",
                "FRI",
                "SAT",
                "SUN",
            ],
            ["06:15", "06:30", "06:45", "True", "True", "True", "True", "True", "True", "False"],
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(initial_data, f)

        try:
            write_yaml_schedule(test_table, "New Schedule", date(2025, 6, 1), None, temp_path)

            # Verify both schedules exist
            with open(temp_path) as f:
                data = yaml.safe_load(f)

            schedules = data["services"]["ctc"]["schedules"]
            assert len(schedules) == 2

            # Should be sorted by start date
            assert schedules[0]["name"] == "Existing Schedule"
            assert schedules[1]["name"] == "New Schedule"

        finally:
            temp_path.unlink(missing_ok=True)

    def test_write_yaml_schedule_replace_existing(self):
        """Test replacing schedule with same start date."""
        # Create initial YAML with schedule on 2025-06-01
        initial_data = {
            "services": {
                "ctc": {
                    "tzid": "America/New_York",
                    "schedules": [{"name": "Old Summer Schedule", "start": date(2025, 6, 1), "ferries": []}],
                }
            }
        }

        test_table = [
            [
                "BUS DEPARTS ROUTE 1",
                "DEPARTS CHEBEAGUE",
                "DEPARTS COUSINS",
                "MON",
                "TUES",
                "WED",
                "THURS",
                "FRI",
                "SAT",
                "SUN",
            ],
            ["06:15", "06:30", "06:45", "True", "True", "True", "True", "True", "True", "False"],
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(initial_data, f)

        try:
            write_yaml_schedule(
                test_table,
                "New Summer Schedule",
                date(2025, 6, 1),  # Same start date
                None,
                temp_path,
            )

            # Verify old schedule was replaced
            with open(temp_path) as f:
                data = yaml.safe_load(f)

            schedules = data["services"]["ctc"]["schedules"]
            assert len(schedules) == 1
            assert schedules[0]["name"] == "New Summer Schedule"

        finally:
            temp_path.unlink(missing_ok=True)

    def test_write_yaml_schedule_empty_table(self):
        """Test writing empty table raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="No data found in table"):
                write_yaml_schedule([], "Test", date.today(), None, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
