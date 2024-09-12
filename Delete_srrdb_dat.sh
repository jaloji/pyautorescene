#!/bin/bash

# Define the file path
FILE="/tmp/www.srrdb.com_session.dat"

# Check if the file exists, and if so, delete it
if [ -f "$FILE" ]; then
    rm -f "$FILE"
fi
