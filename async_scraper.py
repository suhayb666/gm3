import pandas as pd
from bs4 import BeautifulSoup
import time
import random
import re
import tempfile
import shutil
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def extract_fitment_data(soup):
    """
    Extract vehicle fitment data from the product page
    Returns: list of dictionaries with year, make, model, trim, engine
    """
    fitments = []
    
    try:
        # Find the fitment table
        fitment_table = soup.find('table', class_='fitment-table')
        if not fitment_table:
            print("    Warning: fitment-table not found in page HTML")
            return fitments
        
        print("    Debug: fitment-table found in HTML")
        
        # Try to find tbody first, fallback to table
        tbody = fitment_table.find('tbody', class_='fitment-table-body')
        if tbody:
            rows = tbody.find_all('tr', class_='fitment-row')
            print(f"    Debug: Found tbody with {len(rows)} rows")
        else:
            rows = fitment_table.find_all('tr', class_='fitment-row')
            print(f"    Debug: Found table with {len(rows)} rows (no tbody)")
        
        print(f"    Found {len(rows)} fitment rows in table")
        
        for idx, row in enumerate(rows):
            # Try multiple ways to extract text in case structure varies
            year_td = row.find('td', class_='fitment-year')
            make_td = row.find('td', class_='fitment-make')
            model_td = row.find('td', class_='fitment-model')
            trim_td = row.find('td', class_='fitment-trim')
            engine_td = row.find('td', class_='fitment-engine')
            
            # Extract text, handling empty/None cases
            year_text = year_td.text.strip() if year_td and year_td.text else ''
            make_text = make_td.text.strip() if make_td and make_td.text else ''
            model_text = model_td.text.strip() if model_td and model_td.text else ''
            trim_text = trim_td.text.strip() if trim_td and trim_td.text else ''
            engine_text = engine_td.text.strip() if engine_td and engine_td.text else ''
            
            # Only add if we have at least year, make, and model
            if year_text and make_text and model_text:
                fitment = {
                    'Year': year_text,
                    'Make': make_text,
                    'Model': model_text,
                    'Body & Trim': trim_text,
                    'Engine & Transmission': engine_text
                }
                fitments.append(fitment)
                print(f"      Row {idx + 1}: {year_text} {make_text} {model_text}")
            else:
                print(f"      Row {idx + 1}: Skipped (incomplete data)")
        
        if len(fitments) == 0:
            print("    Warning: No valid fitment rows found")
        else:
            print(f"    Successfully extracted {len(fitments)} valid fitment rows")
        
        return fitments
    
    except Exception as e:
        print(f"    Error extracting fitment data: {e}")
        import traceback
        traceback.print_exc()
        return fitments

def create_driver_with_profile():
    """
    Create a headless Chrome driver with a separate temporary profile
    Optimized for AWS EC2 Ubuntu instances
    """
    # Create a temporary directory for this profile
    profile_path = tempfile.mkdtemp(prefix='chrome_profile_')
    
    options = webdriver.ChromeOptions()
    
    # Use the temporary profile directory
    options.add_argument(f'--user-data-dir={profile_path}')
    
    # AWS/Ubuntu critical settings - must come first
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # Headless mode - no browser window
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--ignore-ssl-errors=yes')
    
    # Performance optimizations for AWS
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-sync')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-default-apps')
    
    # Suppress unnecessary logs
    options.add_argument('--log-level=3')
    
    # AWS EC2 specific setuid sandbox
    options.add_argument('--disable-setuid-sandbox')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    return driver, profile_path

def cleanup_profile(profile_path):
    """
    Clean up temporary profile directory
    """
    try:
        shutil.rmtree(profile_path, ignore_errors=True)
    except Exception as e:
        print(f"    Warning: Could not clean up profile directory: {e}")

def extract_product_data(url):
    """
    Extract product data from a Mopar parts page using Selenium
    Returns: list of dictionaries, one for each fitment (year/make/model)
    """
    driver = None
    profile_path = None
    
    try:
        # Create driver with unique profile
        driver, profile_path = create_driver_with_profile()
        print(f"    Created fresh Chrome profile for this request")
        
        driver.get(url)
        
        # Wait for product title to ensure page is loading
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "product-title"))
        )
        print("    Page loaded, product title found")
        
        time.sleep(3)
        
        # Wait for fitment tab to be clickable
        fitment_tab_clicked = False
        try:
            fitment_tab = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "tab-vehicle-fitment-tab"))
            )
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", fitment_tab)
            time.sleep(2)
            fitment_tab.click()
            print("    Clicked vehicle fitment tab")
            time.sleep(6)
            fitment_tab_clicked = True
        except Exception as e:
            print(f"    Note: Could not click fitment tab, will try alternate method")
        
        # Scroll to the fitment section
        try:
            fitment_section = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "product-fitment"))
            )
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", fitment_section)
            time.sleep(3)
            print("    Scrolled to fitment section")
        except Exception as e:
            print(f"    Note: Could not find fitment section")
        
        # Wait for fitment table to be present (before trying to expand)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.fitment-table"))
            )
            print("    Fitment table found in DOM")
            time.sleep(2)
        except Exception as e:
            print(f"    Warning: Fitment table not found in DOM")
        
        # Try to click the fitment expander to reveal all rows
        try:
            expander = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "fitment-expander"))
            )
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", expander)
            time.sleep(1)
            expander.click()
            print("    Clicked fitment expander to reveal all rows")
            time.sleep(7)
        except Exception as e:
            print(f"    Note: No fitment expander found or could not click")
        
        # Aggressive scrolling to trigger lazy loading
        print("    Scrolling to trigger fitment table load...")
        for i in range(8):
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.8)
        
        # Final wait for all fitment rows to be fully rendered
        print("    Waiting for all fitment rows to load...")
        try:
            WebDriverWait(driver, 40).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "tr.fitment-row")) > 0
            )
            # Additional wait to ensure all rows are rendered
            time.sleep(5)
            
            # Get count of rows
            row_count = len(driver.find_elements(By.CSS_SELECTOR, "tr.fitment-row"))
            print(f"    Fitment rows detected: {row_count} rows")
        except Exception as e:
            print(f"    Warning: Timeout waiting for fitment rows")
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        data = {}
        
        # Extract product title
        title_elem = soup.find('h1', class_='product-title')
        data['Product Title'] = title_elem.text.strip() if title_elem else ''
        
        # Extract product subtitle
        subtitle_elem = soup.find('p', class_='product-subtitle')
        data['Product Subtitle'] = subtitle_elem.text.strip() if subtitle_elem else ''
        
        # Extract manufacturer info
        manufacturer_strong = soup.find('strong', string='Genuine Mopar Parts')
        data['Manufacturer Info'] = manufacturer_strong.text.strip() if manufacturer_strong else ''
        
        # Extract fields from ALL field-lists
        field_lists = soup.find_all('ul', class_='field-list')
        field_tracker = {}
        
        for field_list in field_lists:
            items = field_list.find_all('li')
            for item in items:
                label_elem = item.find(['label', 'span'], class_='list-label')
                value_elem = item.find(['span', 'h2'], class_=['list-value', 'sku-display'])
                
                if not label_elem or not value_elem:
                    continue
                
                label = label_elem.text.strip().replace(':', '').strip()
                value = value_elem.text.strip()
                
                if not label or label.startswith('$') or re.match(r'^\d+$', label):
                    continue
                
                if label in field_tracker:
                    field_tracker[label] += 1
                    field_name = f"{label} {field_tracker[label]}"
                else:
                    field_tracker[label] = 1
                    field_name = label
                
                data[field_name] = value
        
        # Extract description
        description_div = soup.find('div', class_='description_body')
        if description_div:
            description_text = description_div.get_text(separator=' ', strip=True)
            data['Description'] = description_text
        
        # Extract notes
        notes_items = soup.find_all('li', class_='notes')
        if notes_items:
            notes_list = [item.get_text(strip=True) for item in notes_items]
            data['Notes'] = ' | '.join(notes_list)
        
        # Extract pricing
        msrp_elem = soup.find('span', class_='list-price-value')
        if msrp_elem:
            data['MSRP'] = msrp_elem.text.strip()
        
        sale_price_elem = soup.find('strong', class_='sale-price-value')
        if sale_price_elem:
            data['Sale Price'] = sale_price_elem.text.strip()
        
        # Extract vehicle fitment data
        fitments = extract_fitment_data(soup)
        
        # Filter to allowed keys
        allowed_keys = [
            'Product Title', 'Product Subtitle', 'Manufacturer Info', 'SKU', 
            'Other Names', 'Description', 'Description 2', 'Replaces',  
            'MSRP', 'Discount', 'Sale Price', 'Condition', 'Install Time', 'Applications', 'Notes'
        ]
        filtered_data = {k: data[k] for k in allowed_keys if k in data}
        
        # Create a row for each fitment
        result_rows = []
        if fitments:
            for fitment in fitments:
                row = filtered_data.copy()
                row.update(fitment)
                result_rows.append(row)
        else:
            row = filtered_data.copy()
            row['Year'] = ''
            row['Make'] = ''
            row['Model'] = ''
            row['Body & Trim'] = ''
            row['Engine & Transmission'] = ''
            result_rows.append(row)
        
        return result_rows
        
    except Exception as e:
        print(f"    Error processing {url}: {e}")
        return None
    finally:
        if driver is not None:
            driver.quit()
        # Clean up the temporary profile
        if profile_path is not None:
            cleanup_profile(profile_path)

def process_excel_file(input_file, output_file=None):
    """
    Process Excel file with product URLs and extract data sequentially
    One URL at a time, with fresh profile for each
    """
    # Read the Excel file
    try:
        df = pd.read_excel(input_file)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    if 'product-image-link href' not in df.columns:
        print("Error: Column 'product-image-link href' not found")
        return
    
    original_columns = list(df.columns)
    print(f"Original columns: {original_columns}\n")
    
    all_rows = []
    total_rows = len(df)
    success_count = 0
    processed_count = 0
    
    # Process URLs sequentially
    for idx, (_, row) in enumerate(df.iterrows()):
        url = row['product-image-link href']
        
        if pd.isna(url) or url == '':
            print(f"Skipping row {idx + 1}: No URL found")
            continue
        
        print(f"Processing {idx + 1}/{total_rows}: {url}")
        
        product_rows = extract_product_data(url)
        
        if product_rows:
            for product_row in product_rows:
                for orig_col in original_columns:
                    if orig_col not in product_row and orig_col in row:
                        product_row[orig_col] = row[orig_col]
            
            all_rows.extend(product_rows)
            success_count += 1
            print(f"  ✓ Data extracted successfully: {len(product_rows)} fitment row(s)\n")
        else:
            print(f"  ✗ Failed to extract data\n")
        
        processed_count += 1
        
        # Save progress every 10 successful extractions
        if success_count % 10 == 0:
            try:
                new_df = pd.DataFrame(all_rows)
                new_df.to_excel(output_file, index=False)
                print(f"\n✓ Progress saved to {output_file} after {success_count} successful extractions ({len(all_rows)} total rows)\n")
            except Exception as e:
                print(f"Error saving progress: {e}\n")
        
        # Random delay between requests
        if idx < total_rows - 1:  # Don't delay after last URL
            delay = random.uniform(3, 6)
            print(f"Waiting {delay:.1f} seconds before next request...\n")
            time.sleep(delay)
    
    # Final save
    if all_rows:
        try:
            final_df = pd.DataFrame(all_rows)
            final_df.to_excel(output_file, index=False)
            print(f"\n✓ Final data saved to {output_file}")
            print(f"  Total rows: {len(final_df)} ({success_count} successful extractions out of {processed_count})")
        except Exception as e:
            print(f"Error saving Excel file: {e}")
    else:
        print(f"\n✗ No data extracted from {processed_count} URLs")

# Main execution
if __name__ == "__main__":
    # Input file path for AWS (Linux path)
    input_dir = "/home/ubuntu/gm2"
    input_file = os.path.join(input_dir, "wheelslist.xlsx")
    
    # Output file path for AWS (Linux path)
    output_dir = "/home/ubuntu/gm2"
    output_file = os.path.join(output_dir, "wheelslist-updated.xlsx")
    
    print("="*70)
    print("Starting sequential web scraping process (headless mode)")
    print("="*70)
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Processing mode: Sequential (one URL at a time)")
    print(f"Profile mode: Fresh Chrome profile for each URL")
    print("="*70 + "\n")
    
    process_excel_file(input_file, output_file)
    
    print("\n" + "="*70)
    print("Process completed!")
    print("="*70)