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
let hasJava = false;
let hasPom = false;
walkDir(root, (filePath) => {
  if (filePath.endsWith('.java')) {
    hasJava = true;
  }
  if (filePath.endsWith('pom.xml')) {
    hasPom = true;
  }
});

console.log(`Java files found: ${hasJava}`);
console.log(`pom.xml found: ${hasPom}`);
