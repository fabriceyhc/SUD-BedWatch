# SUD BedWatch Web Scraper

This directory contains scripts for scraping substance use disorder bed availability data from Los Angeles County's Service & Bed Availability Tool (SBAT).

## Files

- `scrape_sudhelpla.py` - Main scraping script

## Usage

### Basic Usage

```bash
python3 scrape_sudhelpla.py
```

This will:
- Scrape all agency data from the SBAT website
- Save two CSV files in `/home/fabricehc/SUD-BedWatch/data/`:
  - `sudhelpla_agencies_YYYYMMDD_HHMMSS.csv` - Main agency data
  - `sudhelpla_services_YYYYMMDD_HHMMSS.csv` - Service types (currently minimal)

### Command Line Options

```bash
python3 scrape_sudhelpla.py --help
```

Available options:
- `--output-dir, -o` - Specify output directory (default: `/home/fabricehc/SUD-BedWatch/data`)
- `--url, -u` - Specify URL to scrape (default: `https://sapccis.ph.lacounty.gov/sbat/`)
- `--verbose, -v` - Enable verbose logging

### Example with Options

```bash
python3 scrape_sudhelpla.py --verbose --output-dir /path/to/custom/output
```

## Data Schema

The main CSV file contains the following columns:

### Agency Information
- `agency_name` - Primary agency name
- `agency_name_secondary` - Secondary/program name
- `agency_address` - Full address
- `agency_phone` - Phone number
- `agency_website` - Website URL
- `agency_wheelchair_access` - Yes/No for wheelchair accessibility

### Business Hours (for each day of week)
- `agency_hours_{day}_open` - Opening time
- `agency_hours_{day}_close` - Closing time

### Intake Information
- `intake_open_appointments` - Number of available appointments
- `intake_hours_{day}_open` - Intake opening time for each day
- `intake_hours_{day}_close` - Intake closing time for each day

### Services and Population
- `available_beds` - Bed availability information
- `populations_served` - Semicolon-separated list of populations served
- `languages_spoken` - Languages supported

### Metadata
- `last_updated` - When the agency data was last updated

## Automation

This script is designed to be run regularly to track changes in bed availability. You can set up a cron job:

```bash
# Run every hour
0 * * * * cd /home/fabricehc/SUD-BedWatch && python3 scripts/scrape_sudhelpla.py

# Run every 6 hours with verbose logging
0 */6 * * * cd /home/fabricehc/SUD-BedWatch && python3 scripts/scrape_sudhelpla.py --verbose >> logs/scraper.log 2>&1
```

## Requirements

- Python 3.6+
- requests
- beautifulsoup4
- pandas

Install requirements:
```bash
pip3 install requests beautifulsoup4 pandas
```

## Notes

- The script includes error handling and logging
- Files are timestamped to prevent overwrites
- The script is designed to handle the complex nested HTML structure of the SBAT website
- Service types extraction is implemented but may need refinement based on website updates