#!/bin/sh
set -e
PKG=/root/.npm/_npx/9eac9498388ae25e/node_modules/@modelcontextprotocol/inspector
node -e 'const p=require("'"$PKG"'/package.json"); console.log("version", p.version)'
npx --yes @modelcontextprotocol/inspector@latest --web --help 2>&1 | head -40
echo "--- grep catalog ---"
grep -R "No servers configured" "$PKG/clients/web/dist" -l 2>/dev/null | head -5
grep -R "initialServers\|sessionConfig\|readOnlyConfig\|--catalog\|--config" "$PKG/scripts" -n 2>/dev/null | head -40
ls "$PKG/scripts" 2>/dev/null
ls "$PKG/clients" 2>/dev/null
