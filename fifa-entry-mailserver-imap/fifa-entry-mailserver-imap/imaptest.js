const { ImapFlow } = require('imapflow');

async function main() {
    const client = new ImapFlow({
        host: 'mail.clg-esports.com',
        port: 993,
        secure: true,
        auth: {
            user: '',
            pass: ''
        },
        logger: false // Disable debug logging
    });

    try {
        // Connect to Gmail
        console.log('📧 Connecting to Gmail...');
        await client.connect();
        console.log('Connected successfully');

        // Get mailbox lock for INBOX
        let lock = await client.getMailboxLock('INBOX');
        
        try {
            // Test the last resort strategy with specific alias
            const targetEmail = 'coibl68traevis@outlook.com';
            const searchSubject = 'FIFA ID | Validate Your Email';
            const forwardedSubject = 'FW: FIFA ID | Validate Your Email';
            
            console.log(`\n🔍 Testing last resort strategy for: ${targetEmail}`);
            console.log('=' .repeat(60));
            
            // First try standard methods
            let searchResults = [];
            
            // Strategy 1: Original subject FROM target email
            console.log('Searching for original FIFA emails FROM target email...');
            let results1 = await client.search({ 
                subject: searchSubject,
                from: targetEmail
            });
            searchResults = searchResults.concat(results1);
            
            // Strategy 2: Original subject TO target email
            console.log('Searching for original FIFA emails TO target email...');
            let results2 = await client.search({ 
                subject: searchSubject,
                to: targetEmail
            });
            searchResults = searchResults.concat(results2);
            
            // Strategy 3: Forwarded subject FROM target email
            console.log('Searching for forwarded FIFA emails FROM target email...');
            let results3 = await client.search({ 
                subject: forwardedSubject,
                from: targetEmail
            });
            searchResults = searchResults.concat(results3);
            
            // Strategy 4: Forwarded subject TO target email
            console.log('Searching for forwarded FIFA emails TO target email...');
            let results4 = await client.search({ 
                subject: forwardedSubject,
                to: targetEmail
            });
            searchResults = searchResults.concat(results4);
            
            // Strategy 5: Any FIFA subject FROM target email (fallback)
            if (searchResults.length === 0) {
                console.log('No specific FIFA emails found, searching for any FIFA emails FROM target email...');
                let results5 = await client.search({ 
                    subject: 'FIFA',
                    from: targetEmail
                });
                searchResults = searchResults.concat(results5);
            }
            
            // Strategy 6: Any FIFA subject TO target email (fallback)
            if (searchResults.length === 0) {
                console.log('No FIFA emails FROM target email found, searching for any FIFA emails TO target email...');
                let results6 = await client.search({ 
                    subject: 'FIFA',
                    to: targetEmail
                });
                searchResults = searchResults.concat(results6);
            }
            
            // Remove duplicates
            searchResults = [...new Set(searchResults)];
            
            console.log(`Standard methods found ${searchResults.length} FIFA emails for ${targetEmail}`);
            
            // Strategy 7: LAST RESORT - Search for FIFA emails FROM any Outlook account and check HTML content for target alias
            if (searchResults.length === 0) {
                console.log('No FIFA emails found with standard methods, checking emails FROM Outlook accounts for target alias in content...');
                
                // Search for FIFA emails FROM any Outlook account
                let results7 = await client.search({ 
                    subject: 'FIFA',
                    from: '@outlook.com'
                });
                
                console.log(`Found ${results7.length} FIFA emails FROM Outlook accounts`);
                
                // Filter results to only include emails that contain the target email in their content
                const filteredResults = [];
                for (const uid of results7) {
                    try {
                        const message = await client.fetchOne(uid, { 
                            source: true
                        });
                        
                        if (message.source) {
                            const sourceStr = message.source.toString();
                            
                            // Extract HTML content using the same methods as OTP extraction
                            let emailContent = '';
                            
                            // Method 1: Look for multipart HTML content
                            const multipartHtmlMatch = sourceStr.match(/Content-Type: text\/html; charset=[^\r\n]*[\r\n]+([^]*?)(?=Content-Type:|--[a-zA-Z0-9]+--|$)/i);
                            if (multipartHtmlMatch) {
                                emailContent = multipartHtmlMatch[1].trim();
                            }
                            
                            // Method 2: Look for base64 encoded HTML content
                            if (!emailContent) {
                                const base64Match = sourceStr.match(/Content-Type: text\/html[^]*?Content-Transfer-Encoding: base64[^]*?([A-Za-z0-9+\/=\s]+)(?=Content-Type:|--[a-zA-Z0-9]+--|$)/i);
                                if (base64Match) {
                                    try {
                                        const decoded = Buffer.from(base64Match[1].replace(/\s/g, ''), 'base64').toString('utf-8');
                                        emailContent = decoded;
                                    } catch (e) {
                                        // Ignore decode errors
                                    }
                                }
                            }
                            
                            // Method 3: Look for quoted-printable HTML content
                            if (!emailContent) {
                                const qpMatch = sourceStr.match(/Content-Type: text\/html[^]*?Content-Transfer-Encoding: quoted-printable[^]*?([^]*?)(?=Content-Type:|--[a-zA-Z0-9]+--|$)/i);
                                if (qpMatch) {
                                    emailContent = qpMatch[1].trim();
                                }
                            }
                            
                            // Method 4: Look for any HTML tags in the source
                            if (!emailContent) {
                                const htmlTagMatch = sourceStr.match(/(<html[^]*?<\/html>)/i);
                                if (htmlTagMatch) {
                                    emailContent = htmlTagMatch[1];
                                }
                            }
                            
                            // Fallback: Use full source
                            if (!emailContent) {
                                emailContent = sourceStr;
                            }
                            
                            // Check if the target email appears in the content
                            if (emailContent.includes(targetEmail)) {
                                filteredResults.push(uid);
                                console.log(`✅ Found FIFA email with target alias ${targetEmail} in content (UID: ${uid})`);
                            }
                        }
                    } catch (error) {
                        // Ignore errors when checking individual emails
                    }
                }
                
                searchResults = searchResults.concat(filteredResults);
                console.log(`Last resort method found ${filteredResults.length} additional emails`);
            }
            
            // Remove duplicates
            searchResults = [...new Set(searchResults)];
            
            console.log(`\nTotal FIFA emails found for ${targetEmail}: ${searchResults.length}`);
            
            if (searchResults.length === 0) {
                console.log('❌ No emails found with any method');
                return;
            }
            
            // Examine the found emails
            const emailsToExamine = searchResults;
            
            // Examine each FIFA email to understand the structure
            let count = 0;
            for (const uid of emailsToExamine) {
                const message = await client.fetchOne(uid, { 
                    envelope: true, 
                    uid: true,
                    source: true
                });
                
                count++;
                console.log(`\n📧 FIFA Email #${count}:`);
                console.log(`   UID: ${message.uid}`);
                console.log(`   From: ${message.envelope?.from?.[0]?.address || 'Unknown'}`);
                console.log(`   Subject: ${message.envelope?.subject || 'No Subject'}`);
                console.log(`   Date: ${message.envelope?.date || 'Unknown'}`);
                console.log(`   To: ${message.envelope?.to?.map(t => t.address).join(', ') || 'Unknown'}`);
                
                // Extract and examine HTML content
                if (message.source) {
                    const sourceStr = message.source.toString();
                    
                    // Try to extract HTML content
                    let emailContent = '';
                    
                    // Method 1: Look for multipart HTML content
                    const multipartHtmlMatch = sourceStr.match(/Content-Type: text\/html; charset=[^\r\n]*[\r\n]+([^]*?)(?=Content-Type:|--[a-zA-Z0-9]+--|$)/i);
                    if (multipartHtmlMatch) {
                        emailContent = multipartHtmlMatch[1].trim();
                    }
                    
                    // Method 2: Look for base64 encoded HTML content
                    if (!emailContent) {
                        const base64Match = sourceStr.match(/Content-Type: text\/html[^]*?Content-Transfer-Encoding: base64[^]*?([A-Za-z0-9+\/=\s]+)(?=Content-Type:|--[a-zA-Z0-9]+--|$)/i);
                        if (base64Match) {
                            try {
                                const decoded = Buffer.from(base64Match[1].replace(/\s/g, ''), 'base64').toString('utf-8');
                                emailContent = decoded;
                            } catch (e) {
                                console.log(`   Failed to decode base64 content`);
                            }
                        }
                    }
                    
                    // Method 3: Look for any HTML tags in the source
                    if (!emailContent) {
                        const htmlTagMatch = sourceStr.match(/(<html[^]*?<\/html>)/i);
                        if (htmlTagMatch) {
                            emailContent = htmlTagMatch[1];
                        }
                    }
                    
                    if (emailContent) {
                        console.log(`\n📄 HTML Content Preview (first 1000 chars):`);
                        console.log('=' .repeat(60));
                        console.log(emailContent.substring(0, 1000));
                        console.log('=' .repeat(60));
                        
                        // Look for the specific OTP code 562779
                        if (emailContent.includes('562779')) {
                            console.log(`🎯 FOUND TARGET OTP CODE 562779 in HTML content!`);
                        }
                        
                        // Look for email addresses in the HTML content
                        const emailMatches = emailContent.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g);
                        if (emailMatches) {
                            console.log(`\n📧 Email addresses found in HTML content:`);
                            emailMatches.forEach((email, index) => {
                                console.log(`   ${index + 1}. ${email}`);
                            });
                        }
                        
                        // Try to extract OTP code using improved logic
                        let otpCode = null;
                        
                        // Method 1: Look for OTP in <strong> tags (most reliable for FIFA emails)
                        const strongMatch = emailContent.match(/<strong>\s*(\d{6})\s*<\/strong>/i);
                        if (strongMatch) {
                            otpCode = strongMatch[1];
                        }
                        
                        // Method 2: Look for FIFA-specific OTP patterns (avoid placeholder numbers)
                        if (!otpCode) {
                            // Look for 6-digit numbers that are NOT common placeholders
                            const allSixDigitNumbers = emailContent.match(/\b\d{6}\b/g);
                            if (allSixDigitNumbers) {
                                // Filter out common placeholder numbers
                                const validOtpNumbers = allSixDigitNumbers.filter(num => 
                                    num !== '000000' && 
                                    num !== '123456' && 
                                    num !== '111111' && 
                                    num !== '999999' &&
                                    !num.startsWith('000') &&
                                    !num.endsWith('000')
                                );
                                
                                if (validOtpNumbers.length > 0) {
                                    // Take the first valid OTP number
                                    otpCode = validOtpNumbers[0];
                                }
                            }
                        }
                        
                        if (otpCode) {
                            console.log(`\n🔢 OTP Code: ${otpCode}`);
                            if (otpCode === '562779') {
                                console.log(`🎯 FOUND TARGET OTP CODE: ${otpCode} for ${targetEmail}!`);
                            }
                        } else {
                            console.log(`\n❌ No valid OTP code found`);
                        }
                    } else {
                        console.log(`\n❌ No HTML content found`);
                    }
                }
            }
            
            console.log(`\n📊 Examined ${count} FIFA emails`);
            
        } finally {
            lock.release();
        }

    } catch (error) {
        console.error('❌ Error:', error.message);
    } finally {
        await client.logout();
        console.log('Disconnected');
    }
}

main();