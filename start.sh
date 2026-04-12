#!/bin/bash
# Absent Pianist — Start the web interface
# Just double-click this file or run: bash start.sh

cd "$(dirname "$0")"

echo ""
echo "  ============================="
echo "   Absent Pianist"
echo "   Hymn Accompaniment Generator"
echo "  ============================="
echo ""

# Install Flask if not present
pip3 install flask --quiet --break-system-packages 2>/dev/null || pip3 install flask --quiet 2>/dev/null

echo "  Starting web server..."
echo "  Open your browser to: http://localhost:5111"
echo "  Press Ctrl+C to stop"
echo ""

python3 app.py
