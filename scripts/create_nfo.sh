#!/bin/sh
# Script to create NFO files for downloaded DailyWire episodes
# This script is called by yt-dlp after each download

base_name="$1"
tmp_dir="$2"
base_name="${base_name%.*}"
file_name=$(basename "$base_name")
nfo_file="${base_name}.nfo"
json_file="${tmp_dir}/${file_name}.info.json"

# Skip if NFO file already exists
[ -f "$nfo_file" ] && exit 0

# Debug information
echo "Creating NFO file for: $base_name"
echo "Temporary directory: $tmp_dir"
echo "JSON file path: $json_file"

# Check if json file exists
if [ ! -f "$json_file" ]; then
  echo "Error: Json file not found at $json_file"
  exit 0
fi

# Use Python to extract the title and description from JSON
episode_title=$(python3 -c "import json; print(json.load(open(\"$json_file\"))[\"title\"])")
# Remove "[Member Exclusive]" suffix if present
episode_title=$(echo "$episode_title" | sed -E "s/ \[Member Exclusive\]$//")

# Extract description from JSON
description_content=$(python3 -c "import json; print(json.load(open(\"$json_file\")).get(\"description\", \"No description available\"))")

# Create NFO file with proper XML format for Audiobookshelf
echo "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" > "$nfo_file"
echo "<episodedetails>" >> "$nfo_file"
echo "  <title><![CDATA[$episode_title]]></title>" >> "$nfo_file"
echo "  <plot><![CDATA[$description_content]]></plot>" >> "$nfo_file"
echo "</episodedetails>" >> "$nfo_file"

echo "Created NFO file for $(basename "$base_name")"

# Remove the info.json file after creating the NFO file
rm -f "$json_file"
echo "Removed info.json file for $(basename "$base_name")"
