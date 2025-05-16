#!/bin/bash

# Load environment variables from a file
if [ -f /etc/environment ]; then
  source /etc/environment
fi

# Execute the original command with the environment loaded
exec "$@"