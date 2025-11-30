const ImapHelper = require('./helpers/imapHelper');

const testImap = async () => {
    try {
        console.log('🧪 Starting IMAP Helper Test');
        console.log('=' .repeat(50));
        
        const imapHelper = ImapHelper.getInstance();
        
        // Test connection
        console.log('\n1. Testing IMAP connection...');
        const connected = await imapHelper.connect();
        if (!connected) {
            console.error('❌ Failed to connect to IMAP server');
            return;
        }
        console.log('✅ Successfully connected to IMAP server');
        
        // Test email search
        console.log('\n2. Testing FIFA email search...');
        const testEmail = 'grejgoryacovi87@outlook.com';
        const emailCode = await imapHelper.searchForFifaEmail(testEmail);
        
        if (emailCode) {
            console.log(`✅ Found OTP code: ${emailCode}`);
            
            // Validate the OTP format
            if (/^\d{6}$/.test(emailCode)) {
                console.log('✅ OTP code format is valid (6 digits)');
            } else {
                console.log('❌ OTP code format is invalid');
            }
        } else {
            console.log('❌ No OTP code found');
        }
        
        // Test graceful reconnect
        console.log('\n3. Testing graceful reconnect...');
        await imapHelper.gracefulReconnect();
        console.log('✅ Graceful reconnect completed');
        
        // Test disconnect
        console.log('\n4. Testing disconnect...');
        await imapHelper.disconnect();
        console.log('✅ Successfully disconnected');
        
        console.log('\n🎉 All tests completed!');
        
    } catch (error) {
        console.error('❌ Test failed:', error.message);
        console.error(error.stack);
    }
};

// Test OTP extraction with sample HTML content
const testOTPExtraction = () => {
    console.log('\n🧪 Testing OTP Extraction Logic');
    console.log('=' .repeat(50));
    
    // Sample HTML content from FIFA email
    const sampleHTML = `
    <div class="m_329869758002052228text-container" style="text-align:center">
        <span class="im">
            <p>Alternatively, insert the one-time pass code below going into the App and press</p>
            <p>Verify My Code</p>
        </span>
        <p><strong> 296644 </strong><br></p>
        <p><br></p>
    </div>
    <p>Some other content with numbers like 123456 and 149500</p>
    `;
    
    console.log('Sample HTML content:');
    console.log(sampleHTML);
    
    // Current logic (finds first 6-digit number)
    const currentMatch = sampleHTML.match(/\b\d{6}\b/);
    console.log(`\nCurrent logic finds: ${currentMatch ? currentMatch[0] : 'null'}`);
    
    // Improved logic (looks for OTP in specific context)
    const improvedMatch = sampleHTML.match(/<strong>\s*(\d{6})\s*<\/strong>/);
    console.log(`Improved logic finds: ${improvedMatch ? improvedMatch[1] : 'null'}`);
    
    // Alternative improved logic (looks for OTP after "pass code")
    const alternativeMatch = sampleHTML.match(/pass code[^<]*<[^>]*>\s*(\d{6})\s*</);
    console.log(`Alternative logic finds: ${alternativeMatch ? alternativeMatch[1] : 'null'}`);
};

// Run tests
console.log('🚀 FIFA Entry IMAP Helper Test Suite');
console.log('=====================================');

// Test OTP extraction logic first
testOTPExtraction();

// Then run the full IMAP test
testImap();