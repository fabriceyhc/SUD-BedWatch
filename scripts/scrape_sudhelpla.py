#!/usr/bin/env python3
"""
SUD BedWatch - Web Scraper for sudhelpla.org
Extracts agency listings and service information
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import os
import argparse
import logging
from typing import Dict, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SUDHelpLAScraper:
    def __init__(self, base_url: str = "https://sapccis.ph.lacounty.gov/sbat/"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def fetch_page(self) -> BeautifulSoup:
        """Fetch and parse the main page"""
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Error fetching page: {e}")
            raise

    def extract_service_types(self, soup: BeautifulSoup) -> pd.DataFrame:
        """Extract service types and their descriptions with proper namespacing"""
        service_types = []
        
        # Find the filter container
        filter_container = soup.find('div', {'id': 'filterContainer'})
        if not filter_container:
            logger.warning("Filter container not found")
            return pd.DataFrame(columns=['category', 'service_code', 'service_name', 'description'])

        # Find the accordion container
        accordion = filter_container.find('div', {'id': 'accordion'})
        if not accordion:
            logger.warning("Accordion container not found")
            return pd.DataFrame(columns=['category', 'service_code', 'service_name', 'description'])

        # Process each accordion item
        accordion_items = accordion.find_all('div', class_='accordion-item')
        
        for item in accordion_items:
            # Get the accordion header (category)
            header = item.find('h2', class_='accordion-header')
            category = "Unknown"
            if header:
                button = header.find('button')
                if button:
                    category = button.get_text(strip=True).rstrip(':')

            # Get the collapse content
            collapse = item.find('div', class_='accordion-collapse')
            if not collapse:
                continue

            # First, look for tooltips in this section
            tooltips = collapse.find_all('span', class_='fa fa-question-circle')
            tooltip_descriptions = {}
            
            for tooltip in tooltips:
                # Get the description from tooltip attributes
                description = (tooltip.get('title') or 
                              tooltip.get('data-bs-original-title') or 
                              tooltip.get('aria-label', ''))
                
                # Find the associated label in the same container
                container = tooltip.parent
                if container:
                    label_elem = container.find('label')
                    if label_elem:
                        full_service_text = label_elem.get_text(strip=True)
                        tooltip_descriptions[full_service_text] = description

            # Process all checkboxes in this section
            checkboxes = collapse.find_all('input', type='checkbox')
            for checkbox in checkboxes:
                checkbox_id = checkbox.get('id', '')
                # Find associated label
                label_elem = collapse.find('label', {'for': checkbox_id})
                if label_elem:
                    full_service_text = label_elem.get_text(strip=True)
                    
                    if full_service_text:  # Make sure it's not empty
                        # Get description from tooltip if available
                        description = tooltip_descriptions.get(full_service_text, '')
                        
                        # Extract service code and name
                        service_match = re.search(r'^(.+?)\s+\(([^)]+)\)$', full_service_text)
                        if service_match:
                            service_name = service_match.group(1).strip()
                            service_code = service_match.group(2).strip()
                        else:
                            service_name = full_service_text
                            service_code = ''
                        
                        service_types.append({
                            'category': category,
                            'service_code': service_code,
                            'service_name': service_name,
                            'description': description
                        })

        # Remove duplicates based on category + service_name while preserving order
        seen = set()
        unique_services = []
        for service in service_types:
            key = (service['category'], service['service_name'])
            if key not in seen:
                seen.add(key)
                unique_services.append(service)

        return pd.DataFrame(unique_services)

    def parse_hours(self, hours_text: str) -> Dict[str, Dict[str, str]]:
        """Parse business hours text into structured format"""
        hours = {day: {'open': '', 'close': ''} for day in 
                ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']}
        
        if not hours_text:
            return hours

        # Common patterns for hours
        # "Mon-Fri: 9:00 AM - 5:00 PM"
        # "Monday - Friday 8:00AM-5:00PM"
        # "24/7" or "24 hours"
        
        # Handle 24/7 or 24 hours
        if re.search(r'24/?7|24\s*hours', hours_text, re.IGNORECASE):
            for day in hours.keys():
                hours[day] = {'open': '00:00', 'close': '23:59'}
            return hours

        # Handle ranges like "Mon-Fri" or "Monday-Friday"
        day_ranges = re.findall(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?:\s*-\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))?\s*:?\s*(\d{1,2}:\d{2}\s*[AP]M?)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M?)', hours_text, re.IGNORECASE)
        
        day_mapping = {
            'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday', 'thu': 'thursday',
            'fri': 'friday', 'sat': 'saturday', 'sun': 'sunday',
            'monday': 'monday', 'tuesday': 'tuesday', 'wednesday': 'wednesday',
            'thursday': 'thursday', 'friday': 'friday', 'saturday': 'saturday', 'sunday': 'sunday'
        }

        for match in day_ranges:
            start_day, end_day, open_time, close_time = match
            start_day = day_mapping.get(start_day.lower(), start_day.lower())
            end_day = day_mapping.get(end_day.lower(), end_day.lower()) if end_day else start_day

            # Convert time format
            open_24h = self.convert_to_24h(open_time)
            close_24h = self.convert_to_24h(close_time)

            # Apply to day range
            day_list = list(day_mapping.values())
            if start_day in day_list and end_day in day_list:
                start_idx = day_list.index(start_day)
                end_idx = day_list.index(end_day)
                for i in range(start_idx, end_idx + 1):
                    hours[day_list[i]] = {'open': open_24h, 'close': close_24h}

        return hours

    def parse_hours_table(self, table) -> Dict[str, Dict[str, str]]:
        """Parse hours from HTML table"""
        hours = {day: {'open': '', 'close': ''} for day in 
                ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']}
        
        try:
            rows = table.find_all('tr')
            if len(rows) >= 2:
                # First row should have day headers, second row should have times
                header_row = rows[0]
                times_row = rows[1]
                
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                times = [td.get_text(strip=True) for td in times_row.find_all(['th', 'td'])]
                
                day_mapping = {
                    'sun': 'sunday', 'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday',
                    'thu': 'thursday', 'fri': 'friday', 'sat': 'saturday'
                }
                
                for header, time_cell in zip(headers, times):
                    day_key = day_mapping.get(header.lower())
                    if day_key:
                        if 'closed' in time_cell.lower():
                            hours[day_key] = {'open': 'Closed', 'close': 'Closed'}
                        else:
                            # Parse time ranges like "8:00AM - 9:00PM"
                            time_match = re.search(r'(\d{1,2}:\d{2}[AP]M?)\s*-\s*(\d{1,2}:\d{2}[AP]M?)', time_cell)
                            if time_match:
                                open_time = self.convert_to_24h(time_match.group(1))
                                close_time = self.convert_to_24h(time_match.group(2))
                                hours[day_key] = {'open': open_time, 'close': close_time}
        except Exception as e:
            logger.error(f"Error parsing hours table: {e}")
        
        return hours

    def convert_to_24h(self, time_str: str) -> str:
        """Convert 12-hour format to 24-hour format"""
        try:
            # Handle formats like "9:00 AM", "9:00AM", "9AM"
            time_str = re.sub(r'\s+', '', time_str.upper())
            
            if 'AM' in time_str:
                time_part = time_str.replace('AM', '')
                if ':' not in time_part:
                    time_part += ':00'
                hour, minute = time_part.split(':')
                hour = int(hour)
                if hour == 12:
                    hour = 0
                return f"{hour:02d}:{minute}"
            elif 'PM' in time_str:
                time_part = time_str.replace('PM', '')
                if ':' not in time_part:
                    time_part += ':00'
                hour, minute = time_part.split(':')
                hour = int(hour)
                if hour != 12:
                    hour += 12
                return f"{hour:02d}:{minute}"
            else:
                # Assume 24-hour format already
                return time_str
        except:
            return time_str

    def parse_agency_data(self, agency_div) -> Dict:
        """Parse individual agency listing"""
        data = {}

        # Initialize all fields
        data.update({
            'agency_name': '',
            'agency_name_secondary': '',
            'agency_address': '',
            'agency_phone': '',
            'agency_website': '',
            'agency_wheelchair_access': '',
            'available_beds': '',
            'intake_open_appointments': '',
            'populations_served': '',
            'languages_spoken': '',
            'last_updated': ''
        })

        # Add hour fields
        for day in ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']:
            data[f'agency_hours_{day}_open'] = ''
            data[f'agency_hours_{day}_close'] = ''
            data[f'intake_hours_{day}_open'] = ''
            data[f'intake_hours_{day}_close'] = ''

        try:
            # Extract Agency information from 'listing' div
            listing_div = agency_div.find('div', class_='listing')
            if listing_div:
                # Agency name - look for <strong> tag
                name_elem = listing_div.find('strong')
                if name_elem:
                    data['agency_name'] = name_elem.get_text(strip=True)

                # Secondary agency name
                secondary_div = listing_div.find('div', class_='secondname')
                if secondary_div:
                    secondary_span = secondary_div.find('span')
                    if secondary_span:
                        data['agency_name_secondary'] = secondary_span.get_text(strip=True)

                # Address
                address_div = listing_div.find('div', class_='address')
                if address_div:
                    # Extract address text, excluding the direction link
                    address_text = address_div.get_text(strip=True)
                    # Remove the "X.XX miles" part at the beginning
                    address_clean = re.sub(r'^\d+\.\d+\s+miles\s*', '', address_text)
                    data['agency_address'] = address_clean

                # Phone
                phone_div = listing_div.find('div', class_='phone')
                if phone_div:
                    phone_text = phone_div.get_text(strip=True)
                    # Extract just the phone number
                    phone_match = re.search(r'\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}', phone_text)
                    if phone_match:
                        data['agency_phone'] = phone_match.group()

                # Website
                web_div = listing_div.find('div', class_='web')
                if web_div:
                    website_elem = web_div.find('a')
                    if website_elem:
                        data['agency_website'] = website_elem.get('href', '')

                # Wheelchair accessibility
                wheelchair_div = listing_div.find('div', class_='wheel-access')
                if wheelchair_div:
                    wheelchair_text = wheelchair_div.get_text(strip=True)
                    data['agency_wheelchair_access'] = 'Yes' if 'yes' in wheelchair_text.lower() else 'No'

                # Business hours from table
                hours_div = listing_div.find('div', class_='hours')
                if hours_div:
                    table = hours_div.find('table')
                    if table:
                        agency_hours = self.parse_hours_table(table)
                        for day, times in agency_hours.items():
                            data[f'agency_hours_{day}_open'] = times['open']
                            data[f'agency_hours_{day}_close'] = times['close']

            # Extract Available Beds
            beds_div = agency_div.find('div', class_='available-beds')
            if beds_div:
                beds_text = beds_div.get_text(strip=True)
                data['available_beds'] = beds_text

            # Extract Intake Information
            intake_div = agency_div.find('div', class_='intake-info')
            if intake_div:
                intake_text = intake_div.get_text()
                
                # Extract number of open appointments
                appt_match = re.search(r'Open Intake Appts:.*?(\d+)', intake_text)
                if appt_match:
                    data['intake_open_appointments'] = appt_match.group(1)

                # Parse intake hours table if present
                table = intake_div.find('table')
                if table:
                    intake_hours = self.parse_hours_table(table)
                    for day, times in intake_hours.items():
                        data[f'intake_hours_{day}_open'] = times['open']
                        data[f'intake_hours_{day}_close'] = times['close']

            # Extract Populations Served
            service_div = agency_div.find('div', class_='service-type')
            if service_div:
                service_text = service_div.get_text(strip=True)
                # Split by common delimiters and clean up
                populations = re.split(r'(?=[A-Z])', service_text)
                populations = [p.strip() for p in populations if p.strip()]
                data['populations_served'] = '; '.join(populations)

            # Extract Languages Spoken
            languages_div = agency_div.find('div', class_='languages-spoken')
            if languages_div:
                languages_text = languages_div.get_text(strip=True)
                data['languages_spoken'] = languages_text

            # Extract last update
            last_update_div = agency_div.find('div', class_='last-update')
            if last_update_div:
                data['last_updated'] = last_update_div.get_text(strip=True)

        except Exception as e:
            logger.error(f"Error parsing agency data: {e}")

        return data

    def scrape_agencies(self, soup: BeautifulSoup) -> pd.DataFrame:
        """Extract all agency listings"""
        agencies = []

        # Find the main agencies container
        agencies_container = soup.find('div', class_='agencies')
        if not agencies_container:
            logger.error("Agencies container not found")
            return pd.DataFrame()

        # Find all agency listing rows
        agency_rows = agencies_container.find_all('div', class_='agency-listing row')
        logger.info(f"Found {len(agency_rows)} agency listings")

        for i, agency_div in enumerate(agency_rows):
            logger.info(f"Processing agency {i+1}/{len(agency_rows)}")
            agency_data = self.parse_agency_data(agency_div)
            agencies.append(agency_data)

        return pd.DataFrame(agencies)

    def save_data(self, agencies_df: pd.DataFrame, services_df: pd.DataFrame, output_dir: str):
        """Save data to CSV files with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Save agencies data
        agencies_file = os.path.join(output_dir, f"sudhelpla_agencies_{timestamp}.csv")
        agencies_df.to_csv(agencies_file, index=False)
        logger.info(f"Saved {len(agencies_df)} agency records to {agencies_file}")

        # Save services data
        services_file = os.path.join(output_dir, f"sudhelpla_services_{timestamp}.csv")
        services_df.to_csv(services_file, index=False)
        logger.info(f"Saved {len(services_df)} service records to {services_file}")

        return agencies_file, services_file

    def run(self, output_dir: str = "/home/fabricehc/SUD-BedWatch/data") -> Tuple[str, str]:
        """Main scraping workflow"""
        logger.info("Starting SUD BedWatch scraper")
        
        # Fetch page
        logger.info("Fetching page...")
        soup = self.fetch_page()
        
        # Extract service types
        logger.info("Extracting service types...")
        services_df = self.extract_service_types(soup)
        
        # Extract agencies
        logger.info("Extracting agency data...")
        agencies_df = self.scrape_agencies(soup)
        
        # Save data
        logger.info("Saving data...")
        agencies_file, services_file = self.save_data(agencies_df, services_df, output_dir)
        
        logger.info("Scraping completed successfully")
        return agencies_file, services_file

def main():
    parser = argparse.ArgumentParser(description='Scrape SUD BedWatch data from sudhelpla.org')
    parser.add_argument('--output-dir', '-o', 
                       default='/home/fabricehc/SUD-BedWatch/data',
                       help='Output directory for CSV files')
    parser.add_argument('--url', '-u',
                       default='https://sapccis.ph.lacounty.gov/sbat/',
                       help='URL to scrape')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        scraper = SUDHelpLAScraper(args.url)
        agencies_file, services_file = scraper.run(args.output_dir)
        print(f"SUCCESS: Data saved to:")
        print(f"  Agencies: {agencies_file}")
        print(f"  Services: {services_file}")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())