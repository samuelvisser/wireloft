#!/bin/sh
# Script to create NFO files for downloaded DailyWire episodes
# This script is called by yt-dlp after each download

base_name="$1"
tmp_dir="${2:-/tmp/yt-dlp-tmp}"
base_name="${base_name%.*}"
file_name=$(basename "$base_name")
nfo_file="${base_name}.nfo"
desc_file="${tmp_dir}/${file_name}.description"
json_file="${tmp_dir}/${file_name}.info.json"

# Skip if NFO file already exists
[ -f "$nfo_file" ] && exit 0

# Debug information
echo "Creating NFO file for: $base_name"
echo "Temporary directory: $tmp_dir"
echo "Description file path: $desc_file"
echo "JSON file path: $json_file"

# Check if description file exists
if [ ! -f "$desc_file" ]; then
  echo "Warning: Description file not found at $desc_file"
  # Continue anyway, we'll create an NFO file without the description
  description_content="No description available"
else
  description_content=$(cat "$desc_file")
fi

# Extract episode title from JSON metadata if available, otherwise fallback to filename
if [ -f "$json_file" ]; then
  # Use Python to extract the title from JSON
  episode_title=$(python3 -c "import json; print(json.load(open(\"$json_file\"))[\"title\"])")
  # Remove "[Member Exclusive]" suffix if present
  episode_title=$(echo "$episode_title" | sed -E "s/ \[Member Exclusive\]$//")
else
  # Fallback: Extract episode title from filename
  filename=$(basename "$base_name")
  # Remove date prefix and extension to get title
  episode_title=$(echo "$filename" | sed -E "s/^[0-9]{8} - //")
fi

# Create NFO file with proper XML format for Audiobookshelf
echo "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" > "$nfo_file"
echo "<episodedetails>" >> "$nfo_file"
echo "  <title><![CDATA[$episode_title]]></title>" >> "$nfo_file"
echo "  <plot><![CDATA[$description_content]]></plot>" >> "$nfo_file"
echo "</episodedetails>" >> "$nfo_file"

echo "Created NFO file for $(basename "$base_name")"

# Remove the description and info.json files after creating the NFO file if they exist
if [ -f "$desc_file" ]; then
  rm -f "$desc_file"
  echo "Removed description file for $(basename "$base_name")"
fi

if [ -f "$json_file" ]; then
  rm -f "$json_file"
  echo "Removed info.json file for $(basename "$base_name")"
fi
