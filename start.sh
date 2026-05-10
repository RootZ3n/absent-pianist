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

# Install Python dependencies if needed.
pip3 install -r requirements.txt --quiet --break-system-packages 2>/dev/null || pip3 install -r requirements.txt --quiet 2>/dev/null

echo "  Starting web server..."
echo "  Open your browser to: http://localhost:${ABSENT_PIANIST_PORT:-5111}"
echo "  Local-only by default. For LAN access: ABSENT_PIANIST_HOST=0.0.0.0 bash start.sh"
echo "  Press Ctrl+C to stop"
echo ""

python3 app.py
