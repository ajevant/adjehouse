#!/usr/bin/env node

/**
 * Installation script for CAPTCHA solver dependencies
 * This script installs the required packages for image processing
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🔧 Installing CAPTCHA solver dependencies...');

try {
    // Install canvas package
    console.log('📦 Installing canvas package...');
    execSync('npm install canvas@^2.11.2', { stdio: 'inherit' });
    
    console.log('Canvas package installed successfully!');
    
    // Create temp directory for CAPTCHA processing
    const tempDir = path.join(__dirname, 'temp');
    if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir, { recursive: true });
        console.log('📁 Created temp directory for CAPTCHA processing');
    }
    
    console.log('🎉 CAPTCHA solver dependencies installed successfully!');
    console.log('🚀 You can now use the CAPTCHA solver in your automation');
    
} catch (error) {
    console.error('❌ Error installing dependencies:', error.message);
    console.log('\n💡 Manual installation:');
    console.log('   npm install canvas@^2.11.2');
    process.exit(1);
}
