#!/usr/bin/env sh
set -e

# Change to the frontend directory
cd "$(dirname "$0")/../frontend"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

# Run webpack in development mode with watch
echo "Starting frontend development server..."
npm run dev