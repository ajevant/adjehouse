const fs = require('fs');
const path = require('path');

console.log('Creating release package...');

// Create release directory
const releaseDir = './release';
if (!fs.existsSync(releaseDir)) {
    fs.mkdirSync(releaseDir);
}

// Copy executable
const exePath = './dist/fifa-entry-automation.exe';
if (fs.existsSync(exePath)) {
    fs.copyFileSync(exePath, path.join(releaseDir, 'fifa-entry-automation.exe'));
    console.log('Copied Windows executable');
}

// Copy macOS executable
const macPath = './dist/fifa-entry-automation';
if (fs.existsSync(macPath)) {
    fs.copyFileSync(macPath, path.join(releaseDir, 'fifa-entry-automation-mac'));
    console.log('Copied macOS executable');
}

// Copy actual settings file if it exists, otherwise create template
const settingsPath = './settings.txt';
if (fs.existsSync(settingsPath)) {
    fs.copyFileSync(settingsPath, path.join(releaseDir, 'settings.txt'));
    console.log('Copied actual settings.txt');
} else {
    const settingsTemplate = `THREAD_NUM=3
IMAP_SERVER=imap.gmail.com
EMAIL=your-email@gmail.com
IMAP_PASSWORD=your-app-password
DOLPHYN_API_TOKEN=your-dolphin-api-token
DEBUG=FALSE`;
    
    fs.writeFileSync(path.join(releaseDir, 'settings.txt'), settingsTemplate);
    console.log('Created settings.txt template');
}

// Copy information.csv template
const csvTemplate = `EMAIL,PASSWORD,FIRST_NAME,LAST_NAME,STREET_AND_NUMBER,POSTALCODE,CITY,CARD_NUM,EXPIRY_MONTH,EXPIRY_YEAR,CARD_CVV,PHONE_NUMBER,HAS_ACCOUNT,ENTERED,BLOCKED
example@email.com,YourPassword123,John,Doe,123 Main St,1234AB,Amsterdam,4111111111111111,12,2028,123,0612345678,FALSE,FALSE,FALSE`;

fs.writeFileSync(path.join(releaseDir, 'information.csv'), csvTemplate);
console.log('Created information.csv template');

// Create README
const readme = `# FIFA Entry Automation

## Setup Instructions

1. Edit settings.txt with your actual values:
   - THREAD_NUM: Number of concurrent threads (1-20)
   - IMAP_SERVER: Your email IMAP server
   - EMAIL: Your email address for OTP verification
   - IMAP_PASSWORD: Your email app password
   - DOLPHYN_API_TOKEN: Your Dolphin Anty API token
   - DEBUG: Set to TRUE for debug mode, FALSE for production

2. Edit information.csv with user data:
   - Add your FIFA account information
   - One user per row
   - Fill all required fields

3. Run the executable:
   - Windows: fifa-entry-automation.exe
   - macOS: ./fifa-entry-automation-mac

## Requirements

- Dolphin Anty browser installed and running
- Valid proxies configured in Dolphin Anty
- Email account with IMAP access enabled

## Notes

- The application will automatically process all users in information.csv
- Set DEBUG=TRUE in settings.txt to access all development options
- Set DEBUG=FALSE for production mode (only shows start option)
`;

fs.writeFileSync(path.join(releaseDir, 'README.md'), readme);
console.log('Created README.md');

console.log('\n🎉 Release package created in ./release/ directory');
console.log('📁 Contents:');
console.log('   - fifa-entry-automation.exe (Windows)');
console.log('   - fifa-entry-automation-mac (macOS)');
console.log('   - settings.txt (configuration template)');
console.log('   - information.csv (user data template)');
console.log('   - README.md (setup instructions)');
