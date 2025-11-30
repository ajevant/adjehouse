import { ImapFlow } from 'imapflow';
import SettingsHelper from './settingsHelper';

// Types and interfaces
interface ImapConfig {
    host: string;
    port: number;
    secure: boolean;
    auth: {
        user: string;
        pass: string;
    };
    logger: boolean;
}

/**
 * IMAP Helper for reading FIFA verification emails using ImapFlow
 */
class ImapHelper {
    private static instance: ImapHelper;
    private client: any;
    private settings: SettingsHelper;
    private config: ImapConfig;
    private lastReconnectTime: number = 0;

    // Allow instantiating multiple ImapHelper instances (one per worker/thread)
    constructor() {
        this.client = null;
        this.settings = SettingsHelper.getInstance();
        const imapConfig = this.settings.getImapConfig();
        
        this.config = {
            host: imapConfig.server,
            port: 993,
            secure: true,
            auth: {
                user: imapConfig.email,
                pass: imapConfig.password
            },
            logger: false // Disable debug logging
        };
    }

    /**
     * Get the singleton instance of ImapHelper
     * @returns {ImapHelper} - The singleton instance
     */
    static getInstance(): ImapHelper {
        if (!ImapHelper.instance) {
            ImapHelper.instance = new ImapHelper();
        }
        return ImapHelper.instance;
    }

    /**
     * Connect to IMAP server
     */
    async connect(): Promise<boolean> {
        try {
            console.log(`Connecting to IMAP ${this.config.host}...`);
            this.client = new ImapFlow({
                ...this.config,
                logger: false
            });
            await this.client.connect();
            console.log('IMAP connected successfully');
            return true;
        } catch (error: any) {
            console.error(`Failed to connect to ${this.config.host}:`, error.message);
            return false;
        }
    }

    /**
     * Disconnect from IMAP server
     */
    async disconnect(): Promise<void> {
        try {
            if (this.client) {
                await this.client.logout();
                console.log('IMAP disconnected successfully');
            }
        } catch (error: any) {
            console.error('Error disconnecting from IMAP:', error.message);
        }
    }

    /**
     * Gracefully reconnect to refresh IMAP cache
     */
    async gracefulReconnect(): Promise<void> {
        try {
            //console.log('Gracefully reconnecting to refresh IMAP cache...');
            
            // Disconnect if connected
            if (this.client) {
                try {
                    await this.client.logout();
                } catch (logoutError) {
                    // Ignore logout errors, we're reconnecting anyway
                }
                this.client = null;
            }
            
            // Wait a moment before reconnecting
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            // Reconnect
            const connected = await this.connect();
            if (connected) {
                //console.log('Successfully reconnected and refreshed cache');
            } else {
                console.log('Reconnection failed, will retry on next attempt');
            }
            
        } catch (error: any) {
            console.error('Error during graceful reconnect:', error.message);
            // Reset client to null so next attempt will try to connect fresh
            this.client = null;
        }
    }

    /**
     * Wait for FIFA verification email and extract OTP code
     * @param {string} receivingEmail - The catch-all/receiving email address (where emails are delivered)
     * @param {string} accountEmail - The actual account email address (to validate in HTML body)
     * @param {number} maxWaitTime - Maximum wait time in seconds (default: 300 = 5 minutes)
     * @returns {string|null} - OTP code or null if not found
     */
    async waitForFifaOTP(receivingEmail: string, accountEmail: string, maxWaitTime: number = 300): Promise<string | null> {
        try {
            //console.log(`Looking for FIFA verification email for: ${accountEmail} (receiving at: ${receivingEmail})`);
            //console.log(`Will wait up to ${maxWaitTime} seconds for email...`);
            
            const startTime = Date.now();
            let attempts = 0;
            const RECONNECT_INTERVAL = 4; // Reconnect every 8 attempts (40 seconds)
            
            while ((Date.now() - startTime) < (maxWaitTime * 1000)) {
                attempts++;
                
                // Gracefully reconnect every 8 attempts to refresh IMAP cache
                if (attempts % RECONNECT_INTERVAL === 1) {
                    //console.log(`Attempt ${attempts}: Refreshing IMAP connection to clear cache...`);
                    await this.gracefulReconnect();
                }
                
                if (attempts % 6 === 0) { // Log every 30 seconds (6 * 5 seconds)
                    const elapsed = Math.floor((Date.now() - startTime) / 1000);
                    //console.log(`Still looking for FIFA email... (${elapsed}/${maxWaitTime} seconds)`);
                }

                try {
                    const otpCode = await this.searchForFifaEmail(receivingEmail, accountEmail);
                    if (otpCode) {
                        console.log(`Found OTP code: ${otpCode}`);
                        return otpCode;
                    }
                } catch (searchError: any) {
                    console.log(`Search error: ${searchError.message}`);
                }

                // Wait 5 seconds before next check
                await new Promise(resolve => setTimeout(resolve, 5000));
            }
            
            console.log(`FIFA verification email not found after ${maxWaitTime} seconds`);
            return null;
            
        } catch (error: any) {
            console.error('Error waiting for FIFA OTP:', error.message);
            return null;
        }
    }

    /**
     * Check if we need to reconnect based on time (every 20 seconds)
     * @returns {boolean} - true if reconnection is needed
     */
    private shouldReconnect(): boolean {
        const now = Date.now();
        const timeSinceLastReconnect = now - this.lastReconnectTime;
        return timeSinceLastReconnect >= 20000; // 20 seconds
    }

    /**
     * Search for FIFA email and extract OTP (no locks, connect/disconnect managed externally)
     * @param {string} receivingEmail - The catch-all/receiving email address (where emails are delivered)
     * @param {string} accountEmail - The actual account email address (to validate in HTML body)
     * @param {Function} logFunction - Optional logging function
     * @returns {string|null} - OTP code or null if not found
     */
    async searchForFifaEmail(receivingEmail: string, accountEmail: string, logFunction: Function = console.log): Promise<string | null> {
        try {
            // Ensure connected (caller should have called connect())
            if (!this.client) {
                logFunction('IMAP client not connected');
                return null;
            }

            // Open INBOX mailbox before searching (required by ImapFlow)
            logFunction('Opening INBOX mailbox...');
            await this.client.mailboxOpen('INBOX');
            logFunction('INBOX opened successfully');

            // Search for FIFA emails sent TO the receiving email (catch-all), then validate account email in HTML body
            const fiveMinutesAgo = new Date();
            fiveMinutesAgo.setMinutes(fiveMinutesAgo.getMinutes() - 5);
            
            logFunction(`Searching for FIFA emails sent to: ${receivingEmail} (for account: ${accountEmail})`);
            
            // Search for FIFA emails sent TO the receiving email
            let searchResults = await this.client.search({ 
                subject: 'FIFA',
                to: receivingEmail,
                since: fiveMinutesAgo
            });                if (searchResults.length === 0) {
                    logFunction('No FIFA emails found in the last 5 minutes');
                    return null;
                }
                
                logFunction(`Found ${searchResults.length} FIFA email(s)`);
                
                // ALWAYS sort by date to get the most recent email
                const emailData: any[] = [];
                for (const uid of searchResults) {
                    const message = await this.client.fetchOne(uid, { envelope: true });
                    emailData.push({
                        uid: uid,
                        date: message.envelope?.date || new Date(0)
                    });
                }
                
                // Sort by date (most recent first)
                emailData.sort((a, b) => b.date - a.date);
                const sortedResults = emailData.map(item => item.uid);
                
                // Loop through all emails until we find one that matches the target email
                for (let i = 0; i < sortedResults.length; i++) {
                    const uid = sortedResults[i];
                    logFunction(`Processing email ${i + 1}/${sortedResults.length} (UID: ${uid})`);
                    
                const message = await this.client.fetchOne(uid, { 
                    envelope: true, 
                    uid: true,
                    source: true
                });
                
                // Extract OTP code from email content
                let emailContent = '';
                
                if (message.source) {
                    const sourceStr = message.source.toString();
                    
                    // Try multiple methods to extract HTML content
                    
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
                            } catch (e: any) {
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
                    
                    // Method 5: Look for div with text-container class (specific to FIFA emails)
                    if (!emailContent) {
                        const divMatch = sourceStr.match(/(<div[^>]*class="[^"]*text-container[^"]*"[^>]*>[^]*?<\/div>)/i);
                        if (divMatch) {
                            emailContent = divMatch[1];
                        }
                    }
                    
                    // Fallback: Use full source
                    if (!emailContent) {
                        emailContent = sourceStr;
                    }
                    
                    // VALIDATION: Check if this is a forwarded email and validate target email in HTML body
                    const toMatch = emailContent.match(/<b>To:<\/b>\s*([^\s<]+@[^\s<]+)/i);
                    
                    if (toMatch) {
                        const extractedEmail = toMatch[1].toLowerCase().trim();
                        const accountEmailLower = accountEmail.toLowerCase().trim();
                        
                        if (extractedEmail !== accountEmailLower) {
                            logFunction(`Email validation failed: HTML 'To:' (${extractedEmail}) does not match account (${accountEmailLower}), skipping...`);
                            continue; // Skip this email and check the next one
                        }
                        logFunction(`Email validation passed: ${extractedEmail}`);
                    }
                }
                    
                if (emailContent) {
                    // Try multiple extraction methods for FIFA OTP codes
                    let otpCode: string | null = null;
                    
                    // Method 1: Look for OTP in <strong> tags (most reliable for FIFA emails)
                    const strongMatch = emailContent.match(/<strong>\s*(\d{6})\s*<\/strong>/i);
                    if (strongMatch) {
                        otpCode = strongMatch[1];
                    }
                    
                    // Method 1.5: Look for FIFA-specific OTP patterns (avoid placeholder numbers)
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
                    
                    // Method 2: Look for OTP after "pass code" or "verification code" text
                    if (!otpCode) {
                        const passCodeMatch = emailContent.match(/pass code[^<]*<[^>]*>\s*(\d{6})\s*</i);
                        if (passCodeMatch) {
                            otpCode = passCodeMatch[1];
                        }
                    }
                    
                    // Method 3: Look for OTP in verification context
                    if (!otpCode) {
                        const verifyMatch = emailContent.match(/verification[^<]*<[^>]*>\s*(\d{6})\s*</i);
                        if (verifyMatch) {
                            otpCode = verifyMatch[1];
                        }
                    }
                    
                    // Method 4: Look for OTP in FIFA-specific context
                    if (!otpCode) {
                        const fifaMatch = emailContent.match(/FIFA[^<]*<[^>]*>\s*(\d{6})\s*</i);
                        if (fifaMatch) {
                            otpCode = fifaMatch[1];
                        }
                    }
                    
                    // Method 5: Look for OTP after "one-time" text
                    if (!otpCode) {
                        const oneTimeMatch = emailContent.match(/one-time[^<]*<[^>]*>\s*(\d{6})\s*</i);
                        if (oneTimeMatch) {
                            otpCode = oneTimeMatch[1];
                        }
                    }
                    
                    // Method 5.5: German format - Look for OTP after "Meinen Code überprüfen" (My code check)
                    if (!otpCode) {
                        const germanMatch = emailContent.match(/Meinen Code überprüfen[\s\S]{0,200}?(\d{6})/i);
                        if (germanMatch) {
                            otpCode = germanMatch[1];
                        }
                    }
                    
                    // Method 5.6: German format - Look for OTP after "E-Mail-Adresse bestätigen" (Confirm email address)
                    if (!otpCode) {
                        const germanConfirmMatch = emailContent.match(/E-Mail-Adresse bestätigen[\s\S]{0,300}?(\d{6})/i);
                        if (germanConfirmMatch) {
                            otpCode = germanConfirmMatch[1];
                        }
                    }
                    
                    // Method 6: Look for OTP in div with specific class (from your example)
                    if (!otpCode) {
                        const divMatch = emailContent.match(/<div[^>]*class="[^"]*text-container[^"]*"[^>]*>.*?<strong>\s*(\d{6})\s*<\/strong>/is);
                        if (divMatch) {
                            otpCode = divMatch[1];
                        }
                    }
                    
                    // Method 7: Fallback to first 6-digit number (original logic)
                    if (!otpCode) {
                        const fallbackMatch = emailContent.match(/\b\d{6}\b/);
                        if (fallbackMatch) {
                            otpCode = fallbackMatch[0];
                        }
                    }
                    
                    if (otpCode) {
                        logFunction(`OTP code extracted successfully: ${otpCode}`);
                        // Delete the email after successfully extracting OTP code
                        try {
                            await this.client.messageDelete(uid, { uid: true });
                            logFunction(`Email deleted successfully (UID: ${uid})`);
                        } catch (deleteError: any) {
                            logFunction(`Warning: Failed to delete email (UID: ${uid}): ${deleteError.message}`);
                            // Don't fail the whole operation if deletion fails
                        }
                        return otpCode;
                    } else {
                        logFunction(`No 6-digit OTP code found in this email`);
                    }
                } else {
                    logFunction(`No email content found in this email`);
                }
            } // End of for loop
            
            logFunction(`No valid OTP code found in any of the ${sortedResults.length} FIFA email(s)`);
            return null;
            
        } catch (error: any) {
            logFunction(`IMAP Error: ${error.message || error}`, 'error');
            if (error.stack) {
                logFunction(`Stack: ${error.stack}`, 'error');
            }
            return null;
        }
    }

    /**
     * Check if user has account based on CSV data
     * @param {Object} user - User data object
     * @returns {boolean} - True if user has account
     */
    static hasAccount(user: any): boolean {
        if (!user.HAS_ACCOUNT) {
            return false; // Default to false if not specified
        }
        
        const hasAccount = user.HAS_ACCOUNT.toString().toLowerCase();
        return hasAccount === 'true' || hasAccount === '1' || hasAccount === 'yes';
    }
}

export default ImapHelper;