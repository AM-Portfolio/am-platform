import fs from 'fs';
import path from 'path';

function walkDir(dir, callback) {
  fs.readdirSync(dir).forEach(f => {
    let dirPath = path.join(dir, f);
    let isDirectory = fs.statSync(dirPath).isDirectory();
    if (isDirectory) {
      if (f !== 'node_modules' && f !== '.git' && f !== 'venv' && f !== '.ruff_cache') {
        walkDir(dirPath, callback);
      }
    } else {
      callback(dirPath);
    }
  });
}

const root = 'C:/Users/adhik/Downloads/Asrax/AM/am-platform';
walkDir(root, (filePath) => {
  if (filePath.endsWith('.py')) {
    let content = fs.readFileSync(filePath, 'utf8');
    if (content.includes('class ') && content.includes('Enum')) {
      console.log(`File: ${filePath}`);
      const lines = content.split('\n');
      lines.forEach((line, index) => {
        if (line.includes('class ') && line.includes('Enum')) {
          console.log(`  Line ${index + 1}: ${line.trim()}`);
        }
      });
    }
  }
});
