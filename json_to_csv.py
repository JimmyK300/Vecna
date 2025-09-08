#!/usr/bin/env python3
"""
Script to convert all JSON files in media-info folder to a single CSV file.
This script reads all JSON files from data-source/media-info/ directory and 
consolidates them into a single media-info.csv file.
"""

import json
import csv
import os
import glob
from pathlib import Path

def convert_keywords_to_string(keywords):
    """Convert keywords list to a string format that matches the CSV."""
    if isinstance(keywords, list):
        return str(keywords)
    return keywords

def process_json_files():
    """Process all JSON files and append new data to existing CSV format."""
    
    # Define paths
    script_dir = Path(__file__).parent
    json_dir = script_dir / "data-source" / "media-info"
    csv_file = script_dir / "data-source" / "media-info.csv"
    
    # Check if JSON directory exists
    if not json_dir.exists():
        print(f"Error: Directory {json_dir} does not exist!")
        return False
    
    # Define CSV headers (matching the existing CSV structure)
    headers = [
        'author',
        'channel_id', 
        'channel_url',
        'description',
        'keywords',
        'length',
        'publish_date',
        'thumbnail_url',
        'title',
        'watch_url',
        'source_file'
    ]
    
    # Get all JSON files
    json_files = sorted(glob.glob(str(json_dir / "*.json")))
    
    if not json_files:
        print(f"No JSON files found in {json_dir}")
        return False
    
    # Read existing CSV to get already processed files
    existing_source_files = set()
    csv_exists = csv_file.exists()
    
    if csv_exists:
        print(f"Reading existing CSV file: {csv_file}")
        try:
            with open(csv_file, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if 'source_file' in row and row['source_file']:
                        existing_source_files.add(row['source_file'])
            print(f"Found {len(existing_source_files)} existing entries in CSV")
        except Exception as e:
            print(f"Error reading existing CSV: {str(e)}")
            return False
    else:
        print("No existing CSV file found, will create a new one")
    
    # Filter out already processed files
    files_to_process = []
    for json_file_path in json_files:
        filename = os.path.basename(json_file_path)
        if filename not in existing_source_files:
            files_to_process.append(json_file_path)
    
    if not files_to_process:
        print("No new JSON files to process. All files are already in the CSV.")
        return True
    
    print(f"Found {len(files_to_process)} new JSON files to process...")
    
    # Process files and append to CSV
    processed_count = 0
    error_count = 0
    
    # Open CSV in append mode if it exists, write mode if it doesn't
    mode = 'a' if csv_exists else 'w'
    with open(csv_file, mode, newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        
        # Write header only if creating new file
        if not csv_exists:
            writer.writeheader()
        
        for json_file_path in files_to_process:
            try:
                # Extract filename for source_file column
                filename = os.path.basename(json_file_path)
                
                # Read and parse JSON file
                with open(json_file_path, 'r', encoding='utf-8') as jsonfile:
                    data = json.load(jsonfile)
                
                # Prepare row data
                row_data = {
                    'author': data.get('author', ''),
                    'channel_id': data.get('channel_id', ''),
                    'channel_url': data.get('channel_url', ''),
                    'description': data.get('description', ''),
                    'keywords': convert_keywords_to_string(data.get('keywords', [])),
                    'length': data.get('length', ''),
                    'publish_date': data.get('publish_date', ''),
                    'thumbnail_url': data.get('thumbnail_url', ''),
                    'title': data.get('title', ''),
                    'watch_url': data.get('watch_url', ''),
                    'source_file': filename
                }
                
                # Write row to CSV
                writer.writerow(row_data)
                processed_count += 1
                
                # Progress indicator
                if processed_count % 100 == 0:
                    print(f"Processed {processed_count} files...")
                    
            except Exception as e:
                print(f"Error processing {json_file_path}: {str(e)}")
                error_count += 1
                continue
    
    # Summary
    total_existing = len(existing_source_files)
    total_in_csv = total_existing + processed_count
    
    print(f"\nConversion completed!")
    print(f"Files already in CSV: {total_existing}")
    print(f"New files processed: {processed_count}")
    print(f"Errors encountered: {error_count}")
    print(f"Output file: {csv_file}")
    print(f"Total rows in CSV: {total_in_csv + 1} (including header)")
    
    return True

def main():
    """Main function to run the conversion."""
    print("Starting JSON to CSV append operation...")
    print("=" * 50)
    
    success = process_json_files()
    
    if success:
        print("\n" + "=" * 50)
        print("Append operation completed successfully!")
    else:
        print("\n" + "=" * 50)
        print("Append operation failed!")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
