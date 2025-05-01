#!/usr/bin/env python3
import os
import sys
import json
import re

def log(message):
    """Print a log message."""
    print(message)

def main():
    # Check if we have the correct number of arguments
    if len(sys.argv) < 3:
        log("Usage: create_nfo.py <file_path> <tmp_dir>")
        sys.exit(1)
    
    # Get arguments
    base_name = sys.argv[1]
    tmp_dir = sys.argv[2]
    
    # Extract base name without extension
    base_name_no_ext = os.path.splitext(base_name)[0]
    file_name = os.path.basename(base_name_no_ext)
    nfo_file = f"{base_name_no_ext}.nfo"
    
    # Extract the show name from the base_name
    # The format is expected to be /downloads/show-name/episode-name
    path_parts = base_name.split('/')
    show_name = path_parts[-2] if len(path_parts) >= 2 else ""
    
    # Construct the JSON file path with the show name directory
    json_file = os.path.join(tmp_dir, show_name, f"{file_name}.info.json")
    
    # Skip if NFO file already exists
    if os.path.isfile(nfo_file):
        sys.exit(0)
    
    # Debug information
    log(f"Creating NFO file for: {base_name}")
    log(f"Show name: {show_name}")
    log(f"Temporary directory: {tmp_dir}")
    log(f"JSON file path: {json_file}")
    
    # Check if json file exists
    if not os.path.isfile(json_file):
        log(f"Error: Json file not found at {json_file}")
        sys.exit(0)
    
    # Load JSON data
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Extract metadata
    episode_title = data.get("title", "")
    # Remove "[Member Exclusive]" suffix if present
    episode_title = re.sub(r' \[Member Exclusive\]$', '', episode_title)
    
    # Extract description
    description_content = data.get("description", "No description available")
    
    # Extract episode number (meta_movement or meta_track)
    episode_number = data.get("meta_movement") or data.get("meta_track") or ""
    
    # Extract date (meta_date)
    episode_date = data.get("meta_date", "")
    
    # Create NFO file with proper XML format for Audiobookshelf
    with open(nfo_file, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
        f.write('<episodedetails>\n')
        f.write(f'  <title><![CDATA[{episode_title}]]></title>\n')
        f.write(f'  <plot><![CDATA[{description_content}]]></plot>\n')
        if episode_number:
            f.write(f'  <episode>{episode_number}</episode>\n')
        if episode_date:
            f.write(f'  <aired>{episode_date}</aired>\n')
        f.write('</episodedetails>\n')
    
    log(f"Created NFO file for {os.path.basename(base_name_no_ext)}")
    
    # Remove the info.json file after creating the NFO file
    os.remove(json_file)
    log(f"Removed info.json file for {os.path.basename(base_name_no_ext)}")

if __name__ == "__main__":
    main()