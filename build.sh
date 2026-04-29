#!/bin/bash
cd /tmp/skud_build
npm run build
bash /opt/skud/restore_photos.sh
echo "Готово!"
