const { chromium } = require('playwright');
const CsvHelper = require('../helpers/csvHelper');
const ImapHelper = require('../helpers/imapHelper');
const { generateAddress } = require('../helpers/addressHelper');
const DolphinAntyHelper = require('../helpers/dolphinAntyHelper');
const HumanInteractions = require('../helpers/humanInteractions');
const config = require('../helpers/config');
const ProxyHelper = require('../helpers/proxyHelper');
const UtilityHelper = require('../helpers/utilityHelper');
const ProfileHelper = require('../helpers/profileHelper');

class FifaAutomation {
    constructor() {
        this.browser = null;
        this.context = null;
        this.page = null;
        this.isRunning = false;
        this.csvHelper = new CsvHelper();
        this.currentUser = null;
        this.taskNumber = null;
        this.generatedAddress = null; // Store generated address data
        
        // Profile management
        this.profileHelper = new ProfileHelper();
        
        // Proxy management
        this.proxies = null;
        this.assignedProxy = null;
        
        // Human interactions
        this.humanInteractions = null;
    }

    assignProxy(taskNumber) {
        this.assignedProxy = ProxyHelper.assignProxy(this.proxies, taskNumber, this.log.bind(this));
        return this.assignedProxy;
    }

    parseProxy(proxyString) {
        return ProxyHelper.parseProxy(proxyString, this.log.bind(this));
    }


    log(message, level = 'log') {
        UtilityHelper.log(message, level, this.taskNumber);
    }

 
    async createAndStartProfile() {
        return await this.profileHelper.createAndStartProfile(this.proxies, this.taskNumber, this.log.bind(this));
    }

    /**
     * Start the profile and get browser connection details
     * @returns {Promise<boolean>} Success status
     */
    async startProfile() {
        return await this.profileHelper.startProfile(this.log.bind(this));
    }

    /**
     * Stop the current profile
     * @returns {Promise<boolean>} Success status
     */
    async stopProfile() {
        return await this.profileHelper.stopProfile(this.log.bind(this));
    }

    /**
     * Delete the current profile and its associated proxy
     * @returns {Promise<boolean>} Success status
     */
    async deleteProfile() {
        return await this.profileHelper.deleteProfile(this.log.bind(this));
    }

    /**
     * Initialize Playwright browser with stealth settings
     * Uses the browserPath from the started profile
     */
    async initialize() {
        try {
            
            const browserPath = this.profileHelper.getBrowserPath();
            if (!browserPath) {
                throw new Error('Browser path not available. Call createAndStartProfile() first.');
            }
            
            // Connect to existing browser via WebSocket
            const wsEndpoint = `ws://127.0.0.1:${browserPath.port}${browserPath.wsEndpoint}`;
            this.browser = await chromium.connectOverCDP(wsEndpoint);
            
            // Get the default context or create new one with 1920x1080 viewport
            const contexts = this.browser.contexts();
            if (contexts.length > 0) {
                this.context = contexts[0];
            } else {
                this.context = await this.browser.newContext({
                    viewport: { width: 1920, height: 1080 },
                    screen: { width: 1920, height: 1080 },
                    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
                });
               
            }
            
            // Create new page
            this.page = await this.context.newPage();
            
            // Initialize human interactions with the page
            this.humanInteractions = new HumanInteractions(this.page);
            
            // Ensure viewport is set to 1920x1080
            await this.page.setViewportSize({ width: 1920, height: 1080 });
            
            // Verify and log actual browser dimensions
            const dimensions = await this.page.evaluate(() => {
                return {
                    windowWidth: window.innerWidth,
                    windowHeight: window.innerHeight,
                    screenWidth: window.screen.width,
                    screenHeight: window.screen.height,
                    viewportWidth: document.documentElement.clientWidth,
                    viewportHeight: document.documentElement.clientHeight
                };
            });
            
            // debug log
           
            // Force window resize to ensure actual 1920x1080 window size
            try {
                await this.page.evaluate(() => {
                    if (window.resizeTo) {
                        window.resizeTo(1920, 1080);
                    }
                });
               
            } catch (error) {
                this.log('⚠️ Window resize not supported or failed (expected in headless mode)');
            }
            
            // Set extra HTTP headers
            await this.page.setExtraHTTPHeaders({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Sec-Fetch-Dest': 'document'
            });

           
            return true;
        } catch (error) {
            console.error('❌ Failed to initialize Playwright:', error.message);
            throw error;
        }
    }


    /**
     * Wait for page to be fully loaded with human-like behavior
     */
    async waitForPageLoad() {
        this.log('Waiting for page to load...');
        
        try {
            // Wait for network to be idle
            await this.page.waitForLoadState('networkidle', { timeout: 30000 });
            
            // Additional random wait (human behavior)
            await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 750));
            
            // Check for browser error pages after loading
            if (await this.humanInteractions.detectErrorPage()) {
                this.log(`🔄 Browser error page detected after page load - refreshing page...`);
                try {
                    await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                    await this.page.waitForTimeout(3000);
                    this.log('Page refreshed successfully after error page detection');
                    return; // Exit successfully after reload
                } catch (reloadError) {
                    this.log(`⚠️ Page reload failed after error page detection: ${reloadError.message}, continuing...`);
                }
            }
            
            this.log('Page loaded successfully');
        } catch (error) {
            // Check for specific network errors that require page refresh
            if (error.message.includes('ERR_EMPTY_RESPONSE') || 
                error.message.includes('ERR_CONNECTION_CLOSED') ||
                error.message.includes('ERR_TIMED_OUT') ||
                error.message.includes('net::ERR_') ||
                error.message.includes('Navigation timeout') ||
                error.message.includes('Protocol error') ||
                error.message.includes('Target closed') ||
                error.message.includes('Execution context was destroyed')) {
                
                this.log(`🔄 Network error detected during page load: ${error.message} - refreshing page...`);
                try {
                    await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                    await this.page.waitForTimeout(3000);
                    this.log('Page refreshed successfully after network error');
                } catch (reloadError) {
                    this.log(`⚠️ Page refresh failed: ${reloadError.message}, continuing...`);
                }
            } else {
                this.log(`⚠️ Page load warning: ${error.message}, continuing...`);
            }
        }
    }


    /**
     * Wait for new tab to open with auth.fifa.com
     */
    async waitForNewTabWithAuth() {
        try {
            this.log('🔍 Waiting for new tab with auth.fifa.com...');
            
            const maxAttempts = 30; // 30 attempts = 30 seconds max
            let attempts = 0;
            
            while (attempts < maxAttempts) {
                attempts++;
                this.log(`🔄 Attempt ${attempts}/${maxAttempts} - Checking for new tab...`);
                
                // Check if new tab opened with auth URL
                const pages = this.context.pages();
                if (pages.length > 1) {
                    const latestPage = pages[pages.length - 1];
                    const latestUrl = latestPage.url();
                    this.log(`📍 Latest tab URL: ${latestUrl}`);
                    
                    if (latestUrl.includes('auth.fifa.com') || 
                        latestUrl.includes('login') || 
                        latestUrl.includes('signin') ||
                        latestUrl.includes('tickets.fifa.com')) {
                        this.log('Auth tab detected! Switching to new tab...');
                        this.page = latestPage;
                        
                        // Wait for page to load
                        await this.page.waitForLoadState('domcontentloaded', { timeout: 30000 });
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
                        
                        return true;
                    }
                }
                
                // Wait a bit before next check
                await this.page.waitForTimeout(1000);
            }
            
            this.log('⚠️ Auth tab not detected after 30 seconds - proceeding anyway');
            return false;
            
        } catch (error) {
            console.error('❌ Error waiting for auth tab:', error.message);
            return false;
        }
    }

    /**
     * Wait for page to fully load by checking for cookie banner
     * This ensures the page has finished loading and redirecting
     */
    async waitForPageWithCookieBanner() {
        try {
            this.log('🔍 Waiting for cookie banner to appear (indicates page is loaded)...');
            
            const maxAttempts = 80; // 30 attempts = 30 seconds max
            let attempts = 0;
            
            while (attempts < maxAttempts) {
                attempts++;
                this.log(`🔄 Attempt ${attempts}/${maxAttempts} - Checking for cookie banner...`);
                
                try {
                    // Check for CAPTCHA block first before checking for cookie banner (enhanced detection)
                    const isCaptchaBlocked = await this.checkForCaptchaBlock();
                    if (isCaptchaBlocked) {
                        this.log(`🤖 CAPTCHA/DataDome block detected while waiting for cookie banner - proxy/IP is blocked`);
                        throw new Error('CAPTCHA_BLOCKED');
                    }
                    
                    // Check if cookie banner exists using multiple methods
                    const cookieExists = await this.page.evaluate(() => {
                        const button = document.querySelector('#onetrust-accept-btn-handler');
                        return button && button.offsetParent !== null;
                    });
                    
                    if (cookieExists) {
                        this.log('Cookie banner detected - waiting for position to stabilize...');
                        
                        // Wait for cookie banner to stabilize position (ping 5 times)
                        await this.waitForCookieBannerStabilization();
                        
                        this.log('Cookie banner position stabilized - clicking it!');
                        await this.humanInteractions.humanClick('#onetrust-accept-btn-handler');
                        
                        // Verify the cookie banner was actually clicked and dismissed
                        const cookieDismissed = await this.verifyCookieBannerDismissed();
                        if (cookieDismissed) {
                            this.log('Cookie banner clicked and dismissed successfully!');
                            return true;
                        } else {
                            this.log('⚠️ Cookie banner click may have failed - trying alternative methods...');
                            // Try alternative clicking methods
                            const alternativeClicked = await this.tryAlternativeCookieClick();
                            if (alternativeClicked) {
                                this.log('Cookie banner dismissed with alternative method!');
                                return true;
                            } else {
                                this.log('❌ Cookie banner could not be dismissed - this may block other interactions');
                                // Continue anyway but log the issue
                            }
                        }
                    }
                } catch (contextError) {
                    this.log(`⚠️ Context destroyed, retrying... (${contextError.message})`);
                    // Wait for page to stabilize after navigation
                    await this.page.waitForTimeout(2000);
                    continue;
                }
                
                // Wait a bit before next check
                await this.page.waitForTimeout(1000);
                
                try {
                    // Also check if URL has changed (redirects)
                    const currentUrl = this.page.url();
                    this.log(`📍 Current URL: ${currentUrl}`);
                } catch (urlError) {
                    this.log(`⚠️ Cannot get URL, page may be navigating...`);
                }
            }
            
            this.log('⚠️ Cookie banner not found after 30 seconds - proceeding anyway');
            return false;
            
        } catch (error) {
            console.error('❌ Error waiting for cookie banner:', error.message);
            return false;
        }
    }

    /**
     * Wait for cookie banner position to stabilize (ping 5 times)
     */
    async waitForCookieBannerStabilization() {
        try {
            this.log('📍 Waiting for cookie banner position to stabilize...');
            
            let previousPosition = null;
            let stableCount = 0;
            const requiredStableCount = 5;
            
            for (let i = 0; i < 10; i++) { // Max 10 attempts
                try {
                    const position = await this.page.evaluate(() => {
                        const button = document.querySelector('#onetrust-accept-btn-handler');
                        if (button && button.offsetParent !== null) {
                            const rect = button.getBoundingClientRect();
                            return {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            };
                        }
                        return null;
                    });
                    
                    if (position) {
                        this.log(`📍 Cookie banner position: x=${Math.round(position.x)}, y=${Math.round(position.y)}`);
                        
                        // Check if position is the same as previous
                        if (previousPosition && 
                            Math.abs(position.x - previousPosition.x) < 5 && 
                            Math.abs(position.y - previousPosition.y) < 5) {
                            stableCount++;
                            this.log(`Position stable (${stableCount}/${requiredStableCount})`);
                            
                            if (stableCount >= requiredStableCount) {
                                this.log('Cookie banner position is stable!');
                                return true;
                            }
                        } else {
                            stableCount = 0; // Reset if position changed
                            this.log('🔄 Position changed, resetting stability counter');
                        }
                        
                        previousPosition = position;
                    }
                } catch (evalError) {
                    this.log(`⚠️ Position check failed: ${evalError.message}`);
                }
                
                // Wait 200ms before next check
                await new Promise(resolve => setTimeout(resolve, 200));
            }
            
            this.log('⚠️ Cookie banner position may not be fully stable, but proceeding...');
            return false;
            
        } catch (error) {
            console.error('❌ Error waiting for cookie banner stabilization:', error.message);
            return false;
        }
    }

    /**
     * Verify that cookie banner has been dismissed
     */
    async verifyCookieBannerDismissed() {
        try {
            // Wait a moment for the banner to disappear
            await this.page.waitForTimeout(1000);
            
            // Check if cookie banner is still visible
            const cookieStillVisible = await this.page.evaluate(() => {
                const button = document.querySelector('#onetrust-accept-btn-handler');
                return button && button.offsetParent !== null;
            });
            
            if (!cookieStillVisible) {
                this.log('Cookie banner successfully dismissed');
                return true;
            } else {
                this.log('⚠️ Cookie banner still visible after click');
                return false;
            }
        } catch (error) {
            this.log(`⚠️ Error verifying cookie banner dismissal: ${error.message}`);
            return false;
        }
    }

    /**
     * Try alternative methods to click cookie banner
     */
    async tryAlternativeCookieClick() {
        try {
            this.log('🔄 Trying alternative cookie banner clicking methods...');
            
            // Method 1: Try clicking with different selectors
            const alternativeSelectors = [
                'button[aria-label="I Accept"]',
                'button:has-text("I Accept")',
                '.ot-sdk-container button:first-child',
                '#onetrust-button-group button:first-child'
            ];
            
            for (const selector of alternativeSelectors) {
                try {
                    this.log(`🔍 Trying alternative selector: ${selector}`);
                    const element = this.page.locator(selector).first();
                    if (await element.isVisible({ timeout: 2000 })) {
                        await element.click();
                        await this.page.waitForTimeout(1000);
                        
                        // Check if dismissed
                        const dismissed = await this.verifyCookieBannerDismissed();
                        if (dismissed) {
                            this.log(`Cookie banner dismissed with selector: ${selector}`);
                            return true;
                        }
                    }
                } catch (error) {
                    // Continue to next selector
                }
            }
            
            // Method 2: Try JavaScript click
            try {
                this.log('🔍 Trying JavaScript click...');
                await this.page.evaluate(() => {
                    const button = document.querySelector('#onetrust-accept-btn-handler');
                    if (button) {
                        button.click();
                    }
                });
                await this.page.waitForTimeout(1000);
                
                const dismissed = await this.verifyCookieBannerDismissed();
                if (dismissed) {
                    this.log('Cookie banner dismissed with JavaScript click');
                    return true;
                }
            } catch (error) {
                this.log(`⚠️ JavaScript click failed: ${error.message}`);
            }
            
            // Method 3: Try pressing Enter key on the button
            try {
                this.log('🔍 Trying Enter key press...');
                const button = this.page.locator('#onetrust-accept-btn-handler').first();
                if (await button.isVisible({ timeout: 2000 })) {
                    await button.focus();
                    await button.press('Enter');
                    await this.page.waitForTimeout(1000);
                    
                    const dismissed = await this.verifyCookieBannerDismissed();
                    if (dismissed) {
                        this.log('Cookie banner dismissed with Enter key');
                        return true;
                    }
                }
            } catch (error) {
                this.log(`⚠️ Enter key press failed: ${error.message}`);
            }
            
            this.log('❌ All alternative cookie banner methods failed');
            return false;
            
        } catch (error) {
            this.log(`❌ Error trying alternative cookie click: ${error.message}`);
            return false;
        }
    }

    /**
     * Wait for redirect or detect blocked account
     * @param {string} initialUrl - URL before action
     * @param {number} timeoutMs - Timeout in milliseconds
     * @param {string} actionName - Name of the action for logging
     * @returns {string} 'REDIRECTED' or 'BLOCKED'
     */
    async waitForRedirectOrDetectBlock(initialUrl, timeoutMs = 30000, actionName = 'action') {
        try {
            const startTime = Date.now();
            const endTime = startTime + timeoutMs;
            
            while (Date.now() < endTime) {
                const currentUrl = this.page.url();
                
                // Check if URL changed (redirect happened)
                if (currentUrl !== initialUrl) {
                    this.log(`Redirect detected after ${actionName} - URL changed to: ${currentUrl}`);
                    return 'REDIRECTED';
                }
                
                // Check for email verification page elements every few seconds (not blocked, just waiting for email)
                const elapsed2 = Date.now() - startTime;
                
                // Check for email verification every 3 seconds
                if (elapsed2 % 3000 < 1000) {
                    try {
                        this.log(`🔍 Checking for email verification elements... (${Math.round(elapsed2/1000)}s)`);
                        
                        // Use multiple detection methods for email verification
                        
                        // Method 1: Check for OTP input field
                        const otpInputExists = await this.page.locator('input[name="otp"]').isVisible({ timeout: 500 }).catch(() => false);
                        if (otpInputExists) {
                            this.log(`📧 Email verification page detected after ${actionName} - found OTP input field`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 2: Check for "Enter Code" placeholder
                        const enterCodeExists = await this.page.locator('input[placeholder="Enter Code"]').isVisible({ timeout: 500 }).catch(() => false);
                        if (enterCodeExists) {
                            this.log(`📧 Email verification page detected after ${actionName} - found Enter Code field`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 3: Check for "Verify My Code" button
                        const verifyButtonExists = await this.page.locator('button[id="auto-submit"]').isVisible({ timeout: 500 }).catch(() => false);
                        if (verifyButtonExists) {
                            this.log(`📧 Email verification page detected after ${actionName} - found Verify My Code button`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 4: Check for "Check your email" heading
                        const checkEmailHeading = await this.page.locator('h1:has-text("Check your email")').isVisible({ timeout: 500 }).catch(() => false);
                        if (checkEmailHeading) {
                            this.log(`📧 Email verification page detected after ${actionName} - found Check your email heading`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 5: Check for verification container
                        const verifyContainer = await this.page.locator('.verify-content-form-container').isVisible({ timeout: 500 }).catch(() => false);
                        if (verifyContainer) {
                            this.log(`📧 Email verification page detected after ${actionName} - found verification container`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 6: Check page text content
                        const pageText = await this.page.textContent('body').catch(() => '');
                        if (pageText.includes('Check your email') || 
                            pageText.includes('Enter Code') ||
                            pageText.includes('Verify My Code') ||
                            pageText.includes('one click away from completing')) {
                            this.log(`📧 Email verification page detected after ${actionName} - found verification text`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                    } catch (evalError) {
                        this.log(`⚠️ Error checking for email verification: ${evalError.message}`);
                    }
                }
                
                // Check for error messages that indicate issues
                try {
                    const hasError = await this.page.evaluate(() => {
                        const errorElements = document.querySelectorAll('.error, .alert-danger, .invalid-feedback, .inputErrorMsg');
                        return errorElements.length > 0;
                    });
                    
                    if (hasError) {
                        this.log(`⚠️ Error message detected after ${actionName} - not blocked, just error`);
                        return 'ERROR';
                    }
                } catch (evalError) {
                    // Continue waiting
                }
                
                // Log progress every 10 seconds
                const elapsed = Date.now() - startTime;
                if (elapsed % 10000 < 1000) { // Roughly every 10 seconds
                    this.log(`Still waiting for redirect after ${actionName}... (${Math.round(elapsed/1000)}/${Math.round(timeoutMs/1000)}s)`);
                }
                
                await this.page.waitForTimeout(1000); // Wait 1 second before next check
            }
            
            // If we reach here, no redirect happened within timeout
            this.log(`🚫 No redirect after ${actionName} for ${Math.round(timeoutMs/1000)}s - account/proxy appears to be blocked`);
            return 'BLOCKED';
            
        } catch (error) {
            this.log(`⚠️ Error during redirect detection: ${error.message}`);
            return 'ERROR';
        }
    }

    /**
     * Check and dismiss cookie banner during registration process
     */
    async checkAndDismissCookieBannerDuringRegistration() {
        try {
            // Check for cookie banner with multiple selectors
            const cookieBannerSelectors = [
                '.ot-sdk-container',
                '#onetrust-consent-sdk',
                '#onetrust-banner-sdk',
                '[id*="onetrust"]',
                '[class*="cookie"]',
                '[class*="consent"]'
            ];
            
            let bannerFound = false;
            for (const selector of cookieBannerSelectors) {
                try {
                    const banner = this.page.locator(selector);
                    if (await banner.isVisible({ timeout: 1000 })) {
                        this.log(`🍪 Cookie banner detected during registration: ${selector}`);
                        bannerFound = true;
                        break;
                    }
                } catch (error) {
                    // Continue checking other selectors
                }
            }
            
            if (bannerFound) {
                this.log('🍪 Dismissing cookie banner during registration...');
                
                // Try to click accept button
                const acceptSelectors = [
                    '#onetrust-accept-btn-handler',
                    'button:has-text("I Accept")',
                    'button:has-text("Accept")',
                    'button:has-text("Accept All")',
                    '[id*="accept"]'
                ];
                
                let dismissed = false;
                for (const selector of acceptSelectors) {
                    try {
                        const acceptBtn = this.page.locator(selector);
                        if (await acceptBtn.isVisible({ timeout: 1000 })) {
                            await this.humanInteractions.humanClick(selector);
                            this.log(`Cookie banner dismissed during registration: ${selector}`);
                            dismissed = true;
                            break;
                        }
                    } catch (error) {
                        // Continue trying other selectors
                    }
                }
                
                if (!dismissed) {
                    this.log('⚠️ Could not dismiss cookie banner during registration');
                }
                
                // Wait for banner to disappear
                await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
            }
            
        } catch (error) {
            this.log(`⚠️ Error checking cookie banner during registration: ${error.message}`);
        }
    }

    /**
     * Ensure cookie banner is not blocking interactions
     */
    async ensureCookieBannerNotBlocking() {
        try {
            this.log('🔍 Checking if cookie banner is blocking interactions...');
            
            // Check if cookie banner is still visible
            const cookieStillVisible = await this.page.evaluate(() => {
                const button = document.querySelector('#onetrust-accept-btn-handler');
                return button && button.offsetParent !== null;
            });
            
            if (cookieStillVisible) {
                this.log('⚠️ Cookie banner is still visible - attempting to dismiss it...');
                
                // Try to click the cookie banner again
                const dismissed = await this.tryAlternativeCookieClick();
                if (dismissed) {
                    this.log('Cookie banner successfully dismissed');
                } else {
                    this.log('❌ Cookie banner could not be dismissed - this may cause issues');
                }
            } else {
                this.log('Cookie banner is not blocking interactions');
            }
            
            // Wait a moment for any animations to complete
            await this.page.waitForTimeout(1000);
            
        } catch (error) {
            this.log(`⚠️ Error checking cookie banner blocking: ${error.message}`);
        }
    }

    /**
     * Handle cookie banner acceptance
     */
    async handleCookieBanner() {
        try {
            this.log('🍪 Looking for cookie banner...');
            
            // Wait for cookie banner to appear
            const cookieSelectors = [
                '#onetrust-accept-btn-handler',
            ];

            let cookieAccepted = false;
            
            // Try different methods to find and click the cookie button
            try {
                // Method 1: Direct locator
                this.log('🔍 Trying direct locator for cookie button...');
                const cookieButton = this.page.locator('#onetrust-accept-btn-handler');
                
                if (await cookieButton.isVisible({ timeout: 3000 })) {
                    this.log('Found cookie button with locator');
                    await cookieButton.scrollIntoViewIfNeeded();
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
                    await this.humanInteractions.humanClick('#onetrust-accept-btn-handler');
                    cookieAccepted = true;
                    this.log('Cookie banner accepted successfully');
                }
            } catch (error) {
                this.log(`⚠️ Direct locator failed: ${error.message}`);
            }
            
            // Method 2: XPath fallback
            if (!cookieAccepted) {
                try {
                    this.log('🔍 Trying XPath for cookie button...');
                    const cookieButtonXPath = this.page.locator('xpath=//button[@id="onetrust-accept-btn-handler"]');
                    
                    if (await cookieButtonXPath.isVisible({ timeout: 3000 })) {
                        this.log('Found cookie button with XPath');
                        await cookieButtonXPath.scrollIntoViewIfNeeded();
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
                        await this.humanInteractions.humanClick('xpath=//button[@id="onetrust-accept-btn-handler"]');
                        cookieAccepted = true;
                        this.log('Cookie banner accepted successfully');
                    }
                } catch (error) {
                    this.log(`⚠️ XPath failed: ${error.message}`);
                }
            }
            
            // Method 3: Evaluate in browser context
            if (!cookieAccepted) {
                try {
                    this.log('🔍 Trying browser context evaluation...');
                    const clicked = await this.page.evaluate(() => {
                        const button = document.querySelector('#onetrust-accept-btn-handler');
                        if (button && button.offsetParent !== null) {
                            button.click();
                            return true;
                        }
                        return false;
                    });
                    
                    if (clicked) {
                        cookieAccepted = true;
                        this.log('Cookie banner accepted via browser evaluation');
                    }
                } catch (error) {
                    this.log(`⚠️ Browser evaluation failed: ${error.message}`);
                }
            }

            if (!cookieAccepted) {
                this.log('⚠️ No cookie banner found or could not accept cookies');
            }

            // Wait after cookie handling
            await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));

        } catch (error) {
            console.error('❌ Error handling cookie banner:', error.message);
        }
    }

    /**
     * Map address country codes to address form country codes
     * @param {string} addressCountry - Address country code (e.g., 'NED', 'USA', 'MEX')
     * @returns {string} Address form country code
     */
    getCountryCodeForAddress(addressCountry) {
        const countryMapping = {
            'NED': 'NL',    // Netherlands
            'USA': 'US',    // United States
            'MEX': 'MX',    // Mexico
            'GER': 'DE',    // Germany
            'FRA': 'FR',    // France
            'ESP': 'ES',    // Spain
            'ITA': 'IT',    // Italy
            'BRA': 'BR',    // Brazil
            'ARG': 'AR',    // Argentina
            'ENG': 'GB',    // England -> United Kingdom
            'SCO': 'GB',    // Scotland -> United Kingdom
            'WAL': 'GB',    // Wales -> United Kingdom
            'NIR': 'GB',    // Northern Ireland -> United Kingdom
            'IRL': 'IE',    // Republic of Ireland
            'CAN': 'CA',    // Canada
            'JPN': 'JP',    // Japan
            'KOR': 'KR',    // Korea Republic
            'AUS': 'AU',    // Australia
            'BEL': 'BE',    // Belgium
            'POR': 'PT',    // Portugal
            'SUI': 'CH',    // Switzerland
            'AUT': 'AT',    // Austria
            'DEN': 'DK',    // Denmark
            'SWE': 'SE',    // Sweden
            'NOR': 'NO',    // Norway
            'FIN': 'FI',    // Finland
            'POL': 'PL',    // Poland
            'CZE': 'CZ',    // Czech Republic
            'SVK': 'SK',    // Slovakia
            'HUN': 'HU',    // Hungary
            'CRO': 'HR',    // Croatia
            'SRB': 'RS',    // Serbia
            'UKR': 'UA',    // Ukraine
            'RUS': 'RU',    // Russia
            'TUR': 'TR',    // Turkey
            'GRE': 'GR',    // Greece
            'ISR': 'IL',    // Israel
            'EGY': 'EG',    // Egypt
            'MAR': 'MA',    // Morocco
            'TUN': 'TN',    // Tunisia
            'NGA': 'NG',    // Nigeria
            'GHA': 'GH',    // Ghana
            'CMR': 'CM',    // Cameroon
            'SEN': 'SN',    // Senegal
            'CIV': 'CI',    // Côte d'Ivoire
            'RSA': 'ZA',    // South Africa
            'IRN': 'IR',    // IR Iran
            'KSA': 'SA',    // Saudi Arabia
            'QAT': 'QA',    // Qatar
            'UAE': 'AE',    // United Arab Emirates
            'JOR': 'JO',    // Jordan
            'IRQ': 'IQ',    // Iraq
            'ISL': 'IS',    // Iceland
            'ALB': 'AL',    // Albania
            'MKD': 'MK',    // North Macedonia
            'MNE': 'ME',    // Montenegro
            'BIH': 'BA',    // Bosnia and Herzegovina
            'SVN': 'SI',    // Slovenia
            'EST': 'EE',    // Estonia
            'LVA': 'LV',    // Latvia
            'LTU': 'LT',    // Lithuania
            'BLR': 'BY',    // Belarus
            'MDA': 'MD',    // Moldova
            'ARM': 'AM',    // Armenia
            'AZE': 'AZ',    // Azerbaijan
            'GEO': 'GE',    // Georgia
            'KAZ': 'KZ',    // Kazakhstan
            'UZB': 'UZ',    // Uzbekistan
        };
        
        return countryMapping[addressCountry] || 'NL'; // Default to Netherlands
    }


    /**
     * Generate address data based on user's ADDRESS_COUNTRY with retry mechanism
     * @param {Object} user - User data object
     * @param {number} maxRetries - Maximum number of retry attempts (default: 3)
     * @returns {Object|null} Generated address data
     */
    async generateAddressData(user, maxRetries = 3) {
        // Use ADDRESS_COUNTRY for address generation, fallback to FAN_OF, then default to NED
        const countryCode = user?.ADDRESS_COUNTRY || user?.FAN_OF || 'NED';
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                //this.log(`🏠 Generating address for country: ${countryCode} (attempt ${attempt}/${maxRetries})`);
                
                const addressData = await generateAddress(countryCode);
                this.log(`Generated address: ${addressData.STREET_AND_NUMBER}, ${addressData.CITY} ${addressData.POSTALCODE}`);
                
                return addressData;
            } catch (error) {
                this.log(`⚠️ Error generating address (attempt ${attempt}/${maxRetries}): ${error.message}`, 'error');
                
                if (attempt < maxRetries) {
                    this.log(`Waiting 5 seconds before retry...`);
                    await new Promise(resolve => setTimeout(resolve, 5000)); // 5 second delay
                } else {
                    this.log(`❌ Failed to generate address after ${maxRetries} attempts`, 'error');
                    throw new Error(`Failed to generate address for ${countryCode} after ${maxRetries} attempts`);
                }
            }
        }
        
        return null; // Should never reach here
    }

    /**
     * Load user data from CSV
     * @param {number} userIndex - Index of user to load (optional, uses next user if not provided)
     * @returns {Object|null} User data object
     */
    async loadUserData(userIndex = null) {
        try {
            
            // If currentUser is already set (from bulk processing), use it
            if (this.currentUser) {
                // this.log(`Using pre-loaded user: ${this.currentUser.EMAIL}`);
                //this.csvHelper.printUserInfo(this.currentUser);
                
                // Generate address data if not already generated
                if (!this.generatedAddress) {
                    this.generatedAddress = await this.generateAddressData(this.currentUser);
                }
                
                return this.currentUser;
            }
            
            // Read CSV data if not already loaded
            if (this.csvHelper.getUserCount() === 0) {
                await this.csvHelper.readCsvData();
            }

            // Get user data
            let user;
            if (userIndex !== null) {
                user = this.csvHelper.getUserByIndex(userIndex);
            } else {
                user = this.csvHelper.getNextUser();
            }

            if (!user) {
                this.log('No user data available', 'error');
                return null;
            }

            // Task number is already set in startFifaAutomation

            // Validate user data
            const validation = this.csvHelper.validateUser(user);
            if (!validation.isValid) {
                this.log(`Invalid user data: ${JSON.stringify(validation)}`, 'error');
                return null;
            }

            this.currentUser = user;
            
            // Generate address data based on user's FAN_OF country
            this.generatedAddress = await this.generateAddressData(user);
            
            this.csvHelper.printUserInfo(user);
            
            return user;
        } catch (error) {
            this.log(`Error loading user data: ${error.message}`, 'error');
            return null;
        }
    }

    /**
     * Fill email and password fields
     * @param {Object} user - User data object
     */
    async fillLoginForm(user) {
        try {
            this.log('📝 Filling login form...');
            
            if (!user || !user.EMAIL) {
                throw new Error('No user data or email provided');
            }

            // Wait for login form to appear
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 4000));

            // Look for email field
            const emailSelectors = [
                'input[name="email"]',
                'input[id="email"]',
                'input[type="email"]',
                'input[name*="email"]',
                'input[id*="email"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email" i]'
            ];

            // Try different methods to find and fill email field
            let emailFilled = false;
            
            // Method 1: Direct locator (try specific selectors first)
            try {
                this.log('🔍 Trying direct locator for email field...');
                
                // Try more specific selectors first
                const emailSelectors = [
                    'input[name="email"][id="email"]',  // Both name and id
                    'input[name="email"].input100',     // With specific class
                    'input[id="email"].input100',       // ID with class
                    'input[name="email"]'                // Fallback to name only
                ];
                
                let emailField = null;
                for (const selector of emailSelectors) {
                    try {
                        const field = this.page.locator(selector).first();
                        if (await field.isVisible({ timeout: 1000 })) {
                            emailField = field;
                            this.log(`Found email field with selector: ${selector}`);
                            break;
                        }
                    } catch (error) {
                        continue;
                    }
                }
                
                if (emailField) {
                    // Clear the field completely
                    await this.humanInteractions.humanClick('input[name="email"][id="email"]');
                    await emailField.selectText();
                    await emailField.press('Delete');
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 500));
                    
                    // Type email character by character
                    await emailField.type(user.EMAIL, { delay: UtilityHelper.randomDelay(50, 150) });
                    
                    // Verify the email was filled correctly
                    const filledValue = await emailField.inputValue();
                    this.log(`Email filled: ${filledValue} (expected: ${user.EMAIL})`);
                    
                    if (filledValue === user.EMAIL) {
                        emailFilled = true;
                    } else {
                        this.log('⚠️ Email field value mismatch, trying again...');
                        // Try again with different approach
                        await emailField.fill(user.EMAIL);
                        const retryValue = await emailField.inputValue();
                        this.log(`🔄 Retry result: ${retryValue}`);
                        emailFilled = retryValue === user.EMAIL;
                    }
                }
            } catch (error) {
                this.log(`⚠️ Direct locator for email failed: ${error.message}`);
            }
            
            // Method 2: Browser evaluation
            if (!emailFilled) {
                try {
                    this.log('🔍 Trying browser evaluation for email field...');
                    const filled = await this.page.evaluate((email) => {
                        const field = document.querySelector('input[name="email"]') || document.querySelector('input[id="email"]');
                        if (field && field.offsetParent !== null) {
                            field.focus();
                            
                            // Clear field completely
                            field.value = '';
                            field.setAttribute('value', '');
                            
                            // Set the value
                            field.value = email;
                            field.setAttribute('value', email);
                            
                            // Trigger all necessary events
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            field.dispatchEvent(new Event('blur', { bubbles: true }));
                            
                            // Return the actual value to verify
                            return field.value;
                        }
                        return false;
                    }, user.EMAIL);
                    
                    if (filled && filled === user.EMAIL) {
                        emailFilled = true;
                        this.log(`Email filled via browser evaluation: ${filled}`);
                    } else if (filled) {
                        this.log(`⚠️ Email partially filled via browser evaluation: ${filled} (expected: ${user.EMAIL})`);
                        emailFilled = false;
                    }
                } catch (error) {
                    this.log(`⚠️ Browser evaluation for email failed: ${error.message}`);
                }
            }
            
            if (!emailFilled) {
                this.log('❌ Email field not found');
            }

            // Look for password field
            const passwordSelectors = [
                'input[name="password"]',
                'input[id="password"]',
                'input[type="password"]',
                'input[name*="password"]',
                'input[id*="password"]',
                'input[placeholder*="password" i]',
                'input[placeholder*="Password" i]'
            ];

            // Try different methods to find and fill password field
            let passwordFilled = false;
            
            // Method 1: Direct locator (try specific selectors first)
            try {
                this.log('🔍 Trying direct locator for password field...');
                
                // Try more specific selectors first
                const passwordSelectors = [
                    'input[name="password"][id="password"]',  // Both name and id
                    'input[name="password"].input100',        // With specific class
                    'input[id="password"].input100',          // ID with class
                    'input[name="password"]'                   // Fallback to name only
                ];
                
                let passwordField = null;
                for (const selector of passwordSelectors) {
                    try {
                        const field = this.page.locator(selector).first();
                        if (await field.isVisible({ timeout: 1000 })) {
                            passwordField = field;
                            this.log(`Found password field with selector: ${selector}`);
                            break;
                        }
                    } catch (error) {
                        continue;
                    }
                }
                
                if (passwordField) {
                    await this.humanInteractions.humanClick('input[name="password"][id="password"]');
                    await passwordField.fill('');
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 500));
                    await passwordField.type(user.PASSWORD, { delay: UtilityHelper.randomDelay(50, 150) });
                    passwordFilled = true;
                    this.log('Password filled');
                }
            } catch (error) {
                this.log(`⚠️ Direct locator for password failed: ${error.message}`);
            }
            
            // Method 2: Browser evaluation
            if (!passwordFilled) {
                try {
                    this.log('🔍 Trying browser evaluation for password field...');
                    const filled = await this.page.evaluate((password) => {
                        const field = document.querySelector('input[name="password"]') || document.querySelector('input[id="password"]');
                        if (field && field.offsetParent !== null) {
                            field.focus();
                            field.value = '';
                            field.value = password;
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }, user.PASSWORD);
                    
                    if (filled) {
                        passwordFilled = true;
                        this.log('Password filled via browser evaluation');
                    }
                } catch (error) {
                    this.log(`⚠️ Browser evaluation for password failed: ${error.message}`);
                }
            }
            
            if (!passwordFilled) {
                this.log('❌ Password field not found');
            }

            // Wait after filling form
            await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));

        } catch (error) {
            console.error('❌ Error filling login form:', error.message);
            throw error;
        }
    }

    /**
     * Fill login form with robust methods (60-second timeouts)
     */
    async fillLoginFormRobust(user) {
        try {
            this.log('📝 Filling login form with robust methods...');
            
            if (!user || !user.EMAIL) {
                throw new Error('No user data or email provided');
            }

            // Fill email with robust method
            const emailSelectors = [
                'input[name="email"][id="email"]',
                'input[name="email"].input100',
                'input[id="email"].input100',
                'input[name="email"]'
            ];
            
            let emailFilled = false;
            for (const selector of emailSelectors) {
                emailFilled = await this.humanInteractions.robustFill(selector, user.EMAIL, `Email field (${selector})`, null, 2, 60, this.log);
                if (emailFilled) {
                    break;
                }
            }
            
            if (!emailFilled) {
                this.log('❌ All email field selectors failed after 60 seconds - proxy may be blocked');
                return false;
            }

            // Fill password with robust method
            const passwordSelectors = [
                'input[name="password"][id="password"]',
                'input[name="password"].input100',
                'input[id="password"].input100',
                'input[name="password"]'
            ];
            
            let passwordFilled = false;
            for (const selector of passwordSelectors) {
                passwordFilled = await this.humanInteractions.robustFill(selector, user.PASSWORD, `Password field (${selector})`, null, 2, 60, this.log);
                if (passwordFilled) {
                    break;
                }
            }
            
            if (!passwordFilled) {
                this.log('❌ All password field selectors failed after 60 seconds - account may be blocked');
                
                // Check if we're still on the login page - indicates blocked account
                const currentUrl = this.page.url();
                if (currentUrl.includes('auth.fifa.com') && 
                    (currentUrl.includes('authorize') || currentUrl.includes('login'))) {
                    
                    this.log('🚫 Still on login page after 60s - proxy/IP appears to be blocked');
                    
                    // Send blocked login webhook
                    const currentUserData = this.currentUser || {};
                    await this.sendDiscordWebhook(currentUserData, false, 'Login blocked - proxy flagged', false);
                    
                    // Don't mark user as blocked in CSV (it's a proxy issue, not account issue)
                    // Let the main worker handle proxy/profile deletion and retry
                    throw new Error('PROXY_TIMEOUT');
                }
                
                return false;
            }

            this.log('Login form filled successfully with robust methods');
            return true;

        } catch (error) {
            console.error('❌ Error filling login form with robust methods:', error.message);
            return false;
        }
    }


    async checkRegisterResult(){
        // 3 things can happen
            // 1. We go the the password page
            // 2. user already exists so we go to login page
            // 3. Keeps loading and we are blocked 

            // check 5 times for each of the 3 things
            for(let i = 0; i < 5; i++) {

                const isCaptchaBlocked = await this.checkForCaptchaBlock();
                if (isCaptchaBlocked) {
                    this.log('❌ CAPTCHA/DataDome block detected - proxy flagged');
                    throw new Error('CAPTCHA_BLOCKED');
                }

                await this.page.waitForTimeout(5000);
                 // check for user already exists
                const userExistsError = await this.page.locator('.inputErrorMsg:has-text("User already exists")').count() > 0;

                if(userExistsError){
                    return 'USER_EXISTS_SWITCHED_TO_LOGIN';
                }

                // check for password page
                const passwordPage = await this.page.locator('input[name="password"]').count() > 0;
                if(passwordPage){
                    return 'PASSWORD_PAGE';
                }
            }
            // otherwise we are blocked
            return "PROXY_TIMEOUT";
    }

    /**
     * Handle complete account registration flow
     */
    async handleAccountRegistration(user) {
        try {
            this.log('📝 Starting account registration...');
            
            // Step 0: Ensure cookie banner is not blocking the register button
            await this.ensureCookieBannerNotBlocking();
            
            // Step 1: Click SIGN UP button
            const signupClicked = await this.humanInteractions.robustClick('button[id="registerBtn"]', 'SIGN UP button', null, 2, 60, this.log);
            if (!signupClicked) {
                throw new Error('Failed to click SIGN UP button');
            }
            
            // Step 2: Fill registration form
            const formFilled = await this.fillRegistrationForm(user);
            if (!formFilled) {
                throw new Error('Failed to fill registration form');
            }
            
            // Step 3: Click CONTINUE button
            const continueClicked = await this.humanInteractions.robustClick('button[id="btnSubmitRegister"]', 'CONTINUE button', null, 2, 60, this.log);
            if (!continueClicked) {
                throw new Error('Failed to click CONTINUE button');
            }
            
            // Wait for redirect or error after CONTINUE button
            this.log('Waiting for redirect after CONTINUE button...');
            const initialUrl = this.page.url();
            await this.page.waitForTimeout(3000); // Initial wait

            const registerResult = await this.checkRegisterResult()
            if(registerResult === 'USER_EXISTS_SWITCHED_TO_LOGIN'){
                this.log('⚠️ User already exists error detected - updating CSV and switching to login');
                
                // Update CSV to mark account as existing
                const csvHelper = new CsvHelper();
                await csvHelper.readCsvData();
                const accountUpdated = await csvHelper.markAccountCreated(user.EMAIL);
                if (accountUpdated) {
                    this.log('CSV updated: HAS_ACCOUNT = TRUE (user already exists)');
                } else {
                    this.log('⚠️ Failed to update CSV for existing account');
                }
                
                // Click "Sign in" button to switch to login
                const signInClicked = await this.humanInteractions.robustClick('button[data-skbuttonvalue="frmLogin"]', 'Sign in button', null, 2, 60, this.log);
                if (!signInClicked) {
                    // Try alternative selector
                    const altSignInClicked = await this.humanInteractions.robustClick('button:has-text("Sign in")', 'Sign in button (alt)', null, 2, 60, this.log);
                    if (!altSignInClicked) {
                        throw new Error('Failed to click Sign in button after user exists error');
                    }
                }
                
                this.log('Switched to login form - user already exists');
                return 'USER_EXISTS_SWITCHED_TO_LOGIN';
            }else if(registerResult === 'PASSWORD_PAGE'){
                 // Step 4: Fill password form
                const passwordFilled = await this.fillPasswordForm();
                if (!passwordFilled) {
                    throw new Error('Failed to fill password form');
                }
                
                // Step 5: Click CREATE ACCOUNT button
                const createClicked = await this.humanInteractions.robustClick('button[id="btnSubmitRegister"]', 'CREATE ACCOUNT button', null, 2, 60, this.log);
                if (!createClicked) {
                    throw new Error('Failed to click CREATE ACCOUNT button');
                }

                return 'PASSWORD_PAGE';
            }else if(registerResult === 'PROXY_TIMEOUT'){
                throw new Error('PROXY_TIMEOUT');
            }

            

            
            // Check if we're still on the same page after 90 seconds (longer timeout for password form)
            const redirectDetected = await this.waitForRedirectOrDetectBlock(initialUrl, 90000, 'CONTINUE');
            if (redirectDetected === 'BLOCKED') {
                // Proxy/IP is blocked from registering - need to switch proxy and retry
                this.log('🚫 Registration blocked after CONTINUE - proxy/IP is flagged, need to switch');
                
                // Send blocked registration webhook
                const currentUserData = this.currentUser || user;
                await this.sendDiscordWebhook(currentUserData, false, 'Registration blocked after CONTINUE - proxy flagged', false);
                
                // Don't mark user as blocked in CSV (it's a proxy issue, not account issue)
                // Let the main worker handle proxy/profile deletion and retry
                throw new Error('PROXY_TIMEOUT'); // Use PROXY_TIMEOUT to trigger retry logic
            } else if (redirectDetected === 'EMAIL_VERIFICATION') {
                this.log('📧 Email verification detected after CONTINUE - proceeding to email verification');
                // Continue with normal flow - email verification will be handled later
            }
            
            // Additional check: Wait for password form to appear (indicates successful CONTINUE)
            this.log('🔍 Checking if password form appeared after CONTINUE...');
            const passwordFormAppeared = await this.humanInteractions.waitForElementRobust('input[name="password"]', 'Password form after CONTINUE', null, 60, this.log);
            if (passwordFormAppeared === 'RESTART_DRAW_ENTRY' || !passwordFormAppeared) {
                this.log('❌ Password form did not appear after CONTINUE within 90 seconds - registration blocked');
                
                // Send timeout webhook
                const currentUserData = this.currentUser || user;
                await this.sendDiscordWebhook(currentUserData, false, 'Registration timeout - password form did not appear after CONTINUE', false);
                
                // This is a proxy/registration block issue
                throw new Error('PROXY_TIMEOUT');
            }
            
            this.log('Password form appeared - CONTINUE was successful');
            
            // Check for "User already exists" error after CONTINUE button
            this.log('🔍 Checking for "User already exists" error...');
            await this.page.waitForTimeout(2000); // Wait for error to appear
            
            const userExistsError = await this.page.locator('.inputErrorMsg:has-text("User already exists")').count() > 0;
            if (userExistsError) {
                this.log('⚠️ User already exists error detected - updating CSV and switching to login');
                
                // Update CSV to mark account as existing
                const csvHelper = new CsvHelper();
                await csvHelper.readCsvData();
                const accountUpdated = await csvHelper.markAccountCreated(user.EMAIL);
                if (accountUpdated) {
                    this.log('CSV updated: HAS_ACCOUNT = TRUE (user already exists)');
                } else {
                    this.log('⚠️ Failed to update CSV for existing account');
                }
                
                // Click "Sign in" button to switch to login
                const signInClicked = await this.humanInteractions.robustClick('button[data-skbuttonvalue="frmLogin"]', 'Sign in button', null, 2, 60, this.log);
                if (!signInClicked) {
                    // Try alternative selector
                    const altSignInClicked = await this.humanInteractions.robustClick('button:has-text("Sign in")', 'Sign in button (alt)', null, 2, 60, this.log);
                    if (!altSignInClicked) {
                        throw new Error('Failed to click Sign in button after user exists error');
                    }
                }
                
                this.log('Switched to login form - user already exists');
                return 'USER_EXISTS_SWITCHED_TO_LOGIN';
            }
            
            // Step 4: Fill password form
            const passwordFilled = await this.fillPasswordForm();
            if (!passwordFilled) {
                throw new Error('Failed to fill password form');
            }
            
            // Step 5: Click CREATE ACCOUNT button
            const createClicked = await this.humanInteractions.robustClick('button[id="btnSubmitRegister"]', 'CREATE ACCOUNT button', null, 2, 60, this.log);
            if (!createClicked) {
                throw new Error('Failed to click CREATE ACCOUNT button');
            }
            
            // Wait for redirect or error after CREATE ACCOUNT button
            this.log('Waiting for redirect after CREATE ACCOUNT button...');
            const createInitialUrl = this.page.url();
            await this.page.waitForTimeout(3000); // Initial wait
            
            // Check if we're still on the same page after 30 seconds
            const createRedirectDetected = await this.waitForRedirectOrDetectBlock(createInitialUrl, 30000, 'CREATE ACCOUNT');
            if (createRedirectDetected === 'BLOCKED') {
                // Proxy/IP is blocked from creating account - need to switch proxy and retry
                this.log('🚫 Account creation blocked - proxy/IP is flagged, need to switch');
                
                // Send blocked account creation webhook
                const currentUserData = this.currentUser || user;
                await this.sendDiscordWebhook(currentUserData, false, 'Account creation blocked - proxy flagged', false);
                
                // Don't mark user as blocked in CSV (it's a proxy issue, not account issue)
                // Let the main worker handle proxy/profile deletion and retry
                throw new Error('PROXY_TIMEOUT'); // Use PROXY_TIMEOUT to trigger retry logic
            } else if (createRedirectDetected === 'EMAIL_VERIFICATION') {
                this.log('📧 Email verification detected after CREATE ACCOUNT - proceeding to email verification');
                // Continue with normal flow - email verification will be handled later
            }
            
            // Step 6: Handle email verification
            const verified = await this.handleEmailVerification(user);
            if (!verified) {
                throw new Error('Failed to verify email');
            }
            
            this.log('Account registration completed successfully!');
            return true;
            
        } catch (error) {
            console.error('❌ Error during account registration:', error.message);
            return false;
        }
    }

    /**
     * Fill registration form with user data
     */
    async fillRegistrationForm(user) {
        try {
            this.log('📝 Filling registration form...');
            
            // Fill first name (use generated address data)
            const firstName = this.generatedAddress?.FIRST_NAME || user.FIRST_NAME || 'John';
            const firstNameFilled = await this.humanInteractions.robustFill('input[name="firstname"]', firstName, 'First Name', null, 2, 60, this.log);
            if (!firstNameFilled) return false;
            
            // Check for cookie banner after first field
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            // Fill last name (use generated address data)
            const lastName = this.generatedAddress?.LAST_NAME || user.LAST_NAME || 'Doe';
            const lastNameFilled = await this.humanInteractions.robustFill('input[name="lastname"]', lastName, 'Last Name', null, 2, 60, this.log);
            if (!lastNameFilled) return false;
            
            // Check for cookie banner after second field
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            // Fill email
            const emailFilled = await this.humanInteractions.robustFill('input[name="email"]', user.EMAIL, 'Email', null, 2, 60, this.log);
            if (!emailFilled) return false;
            
            // Check for cookie banner after email field
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            // Fill date of birth (realistic selection)
            await this.fillDateOfBirth();
            
            // Check for cookie banner after date of birth
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            // Select country (Netherlands)
            const countrySelected = await this.selectCountryRealistically();
            if (!countrySelected) return false;
            
            // Check for cookie banner after country selection
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            // Select gender (realistic)
            const genderSelected = await this.selectGenderRealistically();
            if (!genderSelected) return false;
            
            // Check for cookie banner after gender selection
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            // Select language (English)
            const languageSelected = await this.selectLanguageRealistically();
            if (!languageSelected) return false;

         
            
            // Check for cookie banner after language selection
            await this.checkAndDismissCookieBannerDuringRegistration();
            
            this.log('Registration form filled successfully');
            return true;
            
        } catch (error) {
            console.error('❌ Error filling registration form:', error.message);
            return false;
        }
    }

    /**
     * Fill date of birth with realistic selection
     */
    async fillDateOfBirth() {
        try {
            this.log('📅 Filling date of birth...');
            
            // Select day (random between 1-28 to avoid month issues)
            const day = Math.floor(Math.random() * 28) + 1;
            await this.humanInteractions.selectDropdownRealistically('select[name="day"]', day.toString(), 'Day', null, this.log);
            
            // Select month (random)
            const month = Math.floor(Math.random() * 12) + 1;
            await this.humanInteractions.selectDropdownRealistically('select[name="month"]', month.toString(), 'Month', null, this.log);
            
            // Select year (random between 1980-1995 for 18+ requirement)
            const year = Math.floor(Math.random() * 16) + 1980; // 1980-1995
            await this.humanInteractions.selectDropdownRealistically('select[name="year"]', year.toString(), 'Year', null, this.log);
            
            this.log(`Date of birth selected: ${day}/${month}/${year}`);
            
        } catch (error) {
            this.log(`⚠️ Error filling date of birth: ${error.message}`);
        }
    }

    /**
     * Select country realistically (Netherlands)
     */
    async selectCountryRealistically() {
        try {
            this.log('🇳🇱 Selecting country (Netherlands)...');
            return await this.humanInteractions.selectDropdownRealistically('select[id="country"]', 'NED', 'Country', null, this.log);
        } catch (error) {
            this.log(`⚠️ Error selecting country: ${error.message}`);
            return false;
        }
    }

    /**
     * Select gender realistically
     */
    async selectGenderRealistically() {
        try {
            this.log('👤 Selecting gender...');
            
            // Click dropdown to open
            const dropdownClicked = await this.humanInteractions.robustClick('select[name="gender"]', 'Gender dropdown', null, 2, 60, this.log);
            if (!dropdownClicked) return false;
            
            await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(300, 600)));
            
            // Type 'M' for Male (realistic keyboard interaction)
            await this.page.keyboard.type('M');
            await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(200, 400)));
            
            // Press Enter to select
            await this.page.keyboard.press('Enter');
            
            this.log('Gender selected: Male');
            return true;
            
        } catch (error) {
            this.log(`⚠️ Error selecting gender: ${error.message}`);
            return false;
        }
    }

    /**
     * Select language realistically (English)
     */
    async selectLanguageRealistically() {
        try {
            this.log('🌐 Selecting language (English)...');
            return await this.humanInteractions.selectDropdownRealistically('select[name="preferredLanguage"]', 'en-GB', 'Language', null, this.log);
        } catch (error) {
            this.log(`⚠️ Error selecting language: ${error.message}`);
            return false;
        }
    }


    /**
     * Fill password form
     */
    async fillPasswordForm() {
        try {
            this.log('🔒 Filling password form...');
            
            // Use the current user data
            const user = this.currentUser;
            if (!user || !user.PASSWORD) {
                throw new Error('No user data or password available');
            }
            
            // Fill password
            const passwordFilled = await this.humanInteractions.robustFill('input[name="password"]', user.PASSWORD, 'Password', null, 2, 60, this.log);
            if (!passwordFilled) return false;
            
            // Fill confirm password
            const confirmFilled = await this.humanInteractions.robustFill('input[name="confirm-password"]', user.PASSWORD, 'Confirm Password', null, 2, 60, this.log);
            if (!confirmFilled) {
                this.log('❌ Confirm password field not found after 60 seconds - checking if account is blocked...');
                
                // Check if we're still on the registration page - indicates blocked account
                const currentUrl = this.page.url();
                if (currentUrl.includes('auth.fifa.com') && 
                    (currentUrl.includes('authorize') || currentUrl.includes('login') || currentUrl.includes('register'))) {
                    
                    this.log('🚫 Still on registration page after 60s - proxy/IP appears to be blocked from registering');
                    
                    // Send blocked registration webhook
                    const currentUserData = this.currentUser || {};
                    await this.sendDiscordWebhook(currentUserData, false, 'Registration form blocked - proxy flagged', false);
                    
                    // Don't mark user as blocked in CSV (it's a proxy issue, not account issue)
                    // Let the main worker handle proxy/profile deletion and retry
                    throw new Error('PROXY_TIMEOUT');
                }
                
                return false;
            }
            
            // Only check Terms and Conditions (required) - skip newsletter and partner consent
            const termsChecked = await this.humanInteractions.robustClick('input[name="TandC"]', 'Terms of Service checkbox', null, 2, 60, this.log);
            if (!termsChecked) return false;
            
            this.log('Password form filled successfully');
            return true;
            
        } catch (error) {
            console.error('❌ Error filling password form:', error.message);
            return false;
        }
    }

    /**
     * Wait for email verification form to appear on the page
     * @returns {boolean} True if form appeared, false if timeout
     */
    async waitForEmailVerificationForm() {
        try {
            const maxAttempts = 60; // 60 seconds max
            let attempts = 0;
            
            while (attempts < maxAttempts) {
                attempts++;
                
                if (attempts % 10 === 0) {
                    this.log(`Still waiting for email verification form... (${attempts}/${maxAttempts}s)`);
                }

                const isCaptchaBlocked = await this.checkForCaptchaBlock();
                if (isCaptchaBlocked) {
                    this.log(`🤖 CAPTCHA/DataDome block detected while waiting for cookie banner - proxy/IP is blocked`);
                    throw new Error('CAPTCHA_BLOCKED');
                }
                
                // Check for specific email verification form elements
                const verificationSelectors = [
                    'input[name="otp"]',
                    'input[name="code"]',
                    'input[name="verificationCode"]',
                    'input[placeholder*="verification" i]',
                    'input[placeholder*="otp" i]',
                    'input[placeholder*="code" i]',
                    'input[id*="verification"]',
                    'input[id*="otp"]',
                    'input[id*="code"]'
                ];
                
                for (const selector of verificationSelectors) {
                    try {
                        const element = this.page.locator(selector);
                        if (await element.isVisible({ timeout: 1000 })) {
                            this.log(`Email verification form ready: ${selector}`);
                            return true;
                        }
                    } catch (error) {
                        // Continue checking other selectors
                    }
                }
                
                // Also check for verification text content
                try {
                    const pageText = await this.page.textContent('body');
                    if (pageText && (
                        pageText.includes('verification code') ||
                        pageText.includes('Verification Code') ||
                        pageText.includes('Enter the code') ||
                        pageText.includes('check your email') ||
                        pageText.includes('Check your email')
                    )) {
                        this.log(`Email verification page ready (found verification text)`);
                        return true;
                    }
                } catch (error) {
                    // Continue waiting
                }
                
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            this.log('❌ Email verification form did not appear after 60 seconds');
            return false;
            
        } catch (error) {
            this.log(`❌ Error waiting for email verification form: ${error.message}`);
            return false;
        }
    }

    /**
     * Handle email verification with IMAP
     */
    async handleEmailVerification(user) {
        try {
            this.log('📧 Starting email verification...');
            
            // Wait for email verification page to load properly
            this.log('Waiting for email verification form to appear...');
            const verificationFormReady = await this.waitForEmailVerificationForm();
            if (!verificationFormReady) {
                this.log('❌ Email verification form did not appear - page may not have redirected yet');
                return false;
            }
            
            // Initialize IMAP helper
            const imapHelper = ImapHelper.getInstance();
            
            // Wait for verification email and extract OTP
            this.log('📧 Waiting for FIFA verification email...');
            const otpCode = await imapHelper.waitForFifaOTP(user.EMAIL, 300); // 5 minutes max
            
            if (!otpCode) {
                this.log('❌ Failed to receive verification email');
                await imapHelper.disconnect();
                return false;
            }
            
            // Fill OTP in verification form
            const otpFilled = await this.humanInteractions.robustFill('input[name="otp"]', otpCode, 'OTP Code', null, 2, 60, this.log);
            if (!otpFilled) {
                await imapHelper.disconnect();
                return false;
            }
            
            // Click Verify My Code button
            const verifyClicked = await this.humanInteractions.robustClick('button[id="auto-submit"]', 'Verify My Code button', null, 2, 60, this.log);
            if (!verifyClicked) {
                await imapHelper.disconnect();
                return false;
            }
            
            // Wait for verification to complete and redirect
            this.log('Waiting for verification redirect...');
            await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(3000, 5000)));
            
            // Check if we got redirected (account creation successful)
            let redirectDetected = false;
            for (let i = 0; i < 10; i++) {
                try {
                    const currentUrl = this.page.url();
                    this.log(`📍 Current URL: ${currentUrl}`);
                    
                    // Check if we're redirected away from verification page
                    if (!currentUrl.includes('verify') && !currentUrl.includes('otp') && !currentUrl.includes('code')) {
                        this.log('Verification redirect detected - account created!');
                        redirectDetected = true;
                        break;
                    }
                } catch (urlError) {
                    this.log(`⚠️ Cannot get URL: ${urlError.message}`);
                }
                
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            if (!redirectDetected) {
                this.log('⚠️ No redirect detected, but continuing...');
            }
            
            await imapHelper.disconnect();
            this.log('Email verification completed successfully!');
            return true;
            
        } catch (error) {
            console.error('❌ Error during email verification:', error.message);
            return false;
        }
    }

    /**
     * Click Learn More button with robust method
     */
    async clickLearnMoreButton(maxRetries = 2) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`🔘 Attempt ${attempt}/${maxRetries} - Looking for "Learn more" button...`);
                
                // Check for CAPTCHA block first before checking for elements
                const isCaptchaBlocked = await this.checkForCaptchaBlock();
                if (isCaptchaBlocked) {
                    this.log(`🤖 CAPTCHA/DataDome block detected while looking for "Learn more" button - proxy/IP is blocked`);
                    throw new Error('CAPTCHA_BLOCKED');
                }
                
                // Check for incorrect page load indicator
                try {
                    const incorrectPageText = await this.page.textContent('body');
                    if (incorrectPageText && incorrectPageText.includes("They think its all over!")) {
                        this.log('⚠️ Detected incorrect page load: "They think its all over!" - refreshing page...');
                        await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 4000));
                        this.log('🔄 Page refreshed, continuing...');
                    }
                } catch (checkError) {
                    this.log(`⚠️ Could not check page content: ${checkError.message}`);
                }
                
                // Look for the "Learn more" button with multiple selectors
                const learnMoreSelectors = [
                    'a[href*="fifa-fwc26-us.tickets.fifa.com"]',
                    'a.card_cardButton__fw+xG',
                    'a:has-text("Learn more")',
                    'a[rel="noopener noreferrer"][target="_blank"]:has-text("Learn more")',
                    'a[href*="tickets.fifa.com"]'
                ];

                let learnMoreClicked = false;
                for (const selector of learnMoreSelectors) {
                    learnMoreClicked = await this.humanInteractions.robustClick(selector, `"Learn more" button (${selector})`, null, 2, 60, this.log);
                    if (learnMoreClicked) {
                        break;
                    }
                }

                if (learnMoreClicked) {
                    this.log(`"Learn more" button clicked successfully on attempt ${attempt}`);
                    return true;
                }

                // If not found and not the last attempt, refresh the page
                if (attempt < maxRetries) {
                    this.log(`❌ "Learn more" button not found on attempt ${attempt}, refreshing page...`);
                    
                    try {
                        await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                        this.log('Page refreshed successfully');
                        
                        // Wait for page to fully load after refresh
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(3000, 5000));
                        
                        // Log page content for debugging
                        try {
                            const pageContent = await this.page.content();
                            this.log('📄 Page content length after refresh:', pageContent.length);
                            
                            // Look for any clickable elements
                            const clickableElements = await this.page.$$eval('a, button, [onclick]', elements => 
                                elements.map(el => ({
                                    tagName: el.tagName,
                                    text: el.textContent?.trim().substring(0, 50),
                                    href: el.href,
                                    className: el.className,
                                    visible: el.offsetParent !== null
                                }))
                            );
                            
                            this.log('🔍 Found clickable elements after refresh:', clickableElements.slice(0, 10));
                        } catch (debugError) {
                            this.log('⚠️ Debug error:', debugError.message);
                        }
                        
                    } catch (refreshError) {
                        this.log(`⚠️ Page refresh failed on attempt ${attempt}:`, refreshError.message);
                    }
                } else {
                    this.log('❌ All "Learn more" button selectors failed after all attempts');
                    
                    // Log page content for debugging
                    try {
                        const pageContent = await this.page.content();
                        this.log('📄 Page content length:', pageContent.length);
                        
                        // Look for any clickable elements
                        const clickableElements = await this.page.$$eval('a, button, [onclick]', elements => 
                            elements.map(el => ({
                                tagName: el.tagName,
                                text: el.textContent?.trim().substring(0, 50),
                                href: el.href,
                                className: el.className,
                                visible: el.offsetParent !== null
                            }))
                        );
                        
                        this.log('🔍 Found clickable elements:', clickableElements.slice(0, 10));
                    } catch (debugError) {
                        this.log('⚠️ Debug error:', debugError.message);
                    }
                    
                    return false;
                }
                
            } catch (error) {
                console.error(`❌ Error on attempt ${attempt} to click "Learn more" button:`, error.message);
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to click "Learn more" button after ${maxRetries} attempts`);
                    return false;
                }
                
                // Wait before retry
                this.log(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Handle login result and check for redirects
     */
    async handleLoginResult() {
        try {
            this.log('Waiting for login result...');
            
            const initialUrl = this.page.url();
            this.log(`📍 Initial URL before login check: ${initialUrl}`);
            
            // Wait for potential redirects with longer timeout for blocked accounts
            await this.page.waitForTimeout(UtilityHelper.randomDelay(3000, 5000));
            
            // Check if new tab opened (successful login)
            const pages = this.context.pages();
            // Make sure our context is on latest page
            this.page = pages[pages.length - 1];

            // Check for CAPTCHA block first before checking for elements
            const isCaptchaBlocked = await this.checkForCaptchaBlock();
            if (isCaptchaBlocked) {
                this.log(`🤖 CAPTCHA/DataDome block detected - proxy/IP is blocked`);
                throw new Error('CAPTCHA_BLOCKED');
            }

            // Now we could have 4 options 
            // 1. we are still on login page and are blocked
            // 2. We are on email verfictation page
            // 3. We are on complete your account page (so wehere you fill your address shit)
            // 4. We are on lottery applications page with enter draw button

            // first wait for page content to be loaded
            await this.page.waitForLoadState('domcontentloaded', { timeout: 30000 });

            await this.page.waitForTimeout(5000);


            // best way to cehck this is propbably the page title
            const pageTitle = await this.page.title();
            this.log(`📄 Page title: ${pageTitle}`);
            
            // Both email otp and Blocked account will have FIFA Login in the title
            for(let i = 0; i < 5; i++) {
                await this.page.waitForTimeout(5000);
                if(pageTitle.includes('FIFA Login')) {
                    this.log('Still on login page, email verfication or blocked')
                    const isEmailVerification = await this.checkIfEmailVerificationNeeded();

                    if (isEmailVerification) {
                            this.log('📧 Detected email verification page');
                            return 'EMAIL_VERIFICATION_NEEDED';
                    }
                }else if(pageTitle.includes('Complete your account - FIFA')) {
                    // we are on account completion page
                    this.log('On account completion page, filling form...');
                    return 'ACCOUNT_COMPLETION_NEEDED';
                }else if(pageTitle.includes('Draw Entry - FIFA')) {
                    // we are on draw entry page
                    this.log('On draw entry page');
                    return 'DRAW_ENTRY_NEEDED';
                }
            }
            return "PROXY_TIMEOUT";
            
        } catch (error) {
            console.error('❌ Error handling login result:', error.message);
            return false;
        }
    }

    /**
     * Handle account completion form
     */
    async handleAccountCompletion(user) {
        try {
            this.log('📝 Handling account completion...');
            
            // Wait for page to load
            await this.page.waitForLoadState('domcontentloaded', { timeout: 30000 });
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
            
            // Check what page we're on
            const pageTitle = await this.page.title();
            this.log(`📄 Page title: ${pageTitle}`);
            
            if (pageTitle.includes('Complete your account')) {
                this.log('On account completion page, filling form...');
                await this.fillAccountCompletionForm(user);
            } else if (pageTitle.includes('Draw Entry') || pageTitle.includes('FIFA World Cup')) {
                this.log('On FIFA World Cup draw entry page, handling draw entry...');
                const drawEntryResult = await this.handleDrawEntry();
                if (drawEntryResult === 'RESTART_DRAW_ENTRY') {
                    this.log('🔄 Page reloaded during draw entry - restarting from draw entry');
                    await this.handleDrawEntry();
                }
                return;
            } else {
                this.log('⚠️ Unknown page, trying to proceed...');
                return;
            }
        } catch (error) {
            console.error('❌ Error handling account completion:', error.message);
            throw error;
        }
    }

    /**
     * Fill the account completion form
     */
    async fillAccountCompletionForm(user) {
        try {
            
            // 1. Click "I am at least 18 years old" checkbox
            await this.checkAgeConfirmation();
            
            // 2. Select all tournament rounds
            await this.selectTournamentRounds();
            
            // 3. Select "I am a Fan of: Netherlands"
            await this.selectFanCountry();
            
            // 4. Select random 4 venues
            await this.selectRandomVenues();
            
            // 5. Fill address information
            await this.fillAddressInfo(user);
            
            // 6. Fill phone number with NL country code
            await this.fillPhoneNumber(user);
            
            // Submit the form
            await this.submitAccountForm();
            
            this.log('Account completion form filled successfully!');
            
            // Wait for redirect to lottery applications page
            this.log('Waiting for redirect to lottery applications page...');
            await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(5000, 10000)));
            
            // Check if we're redirected to lottery applications
            const currentUrl = this.page.url();
            this.log(`📍 Current URL after form submission: ${currentUrl}`);
            
            if (currentUrl.includes('lotteryApplications')) {
                this.log('Redirected to lottery applications page - continuing with draw entry...');
                const drawEntryResult = await this.handleDrawEntry();
                if (drawEntryResult === 'RESTART_DRAW_ENTRY') {
                    this.log('🔄 Page reloaded during draw entry - restarting from draw entry');
                    await this.handleDrawEntry();
                }
                
                // After draw entry is complete, check for completion and send webhook
                await this.handleCompletionAndWebhook(user);
            } else {
                this.log('⚠️ Not on lottery applications page, may need manual intervention');
            }
            
        } catch (error) {
            console.error('❌ Error filling account completion form:', error.message);
            throw error;
        }
    }

    /**
     * Handle FIFA World Cup draw entry page
     */
    async handleDrawEntry(maxRetries = 2) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`🎟️ Attempt ${attempt}/${maxRetries} - Handling FIFA World Cup draw entry...`);

            const isCaptchaBlocked = await this.checkForCaptchaBlock();
            if (isCaptchaBlocked) {
                this.log(`🤖 CAPTCHA/DataDome block detected - proxy/IP is blocked`);
                throw new Error('CAPTCHA_BLOCKED');
            }
            
            // Wait for page to fully load
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
            
            // Step 1: Click "Enter Draw", "Apply", or "Yes" button (different pages have different buttons)
            const enterDrawSelectors = [
                // Standard flow buttons (for existing logged-in users)
                'button[aria-label="Enter Draw"]',                                 // Standard Enter Draw button
                'button:has-text("Enter Draw")',                                   // Enter Draw text match
                '.sc-kLgnNl:has-text("Enter Draw")',                              // Enter Draw with class
                // Direct access page buttons
                'button[aria-label="Apply"]',                                       // Direct access page
                'button:has-text("Apply")',                                        // Direct access page
                '.sc-kLgnNl:has-text("Apply")',
                // New registration flow - Yes/No buttons (for newly registered users)
                'button.yes-btn',                                                    // Yes button for new users
                'button:has-text("Enter the FIFA World Cup 26™ Presale Draw")',    // Yes button text match
                '.yes-btn',                                                         // Yes button class
                // Fallback
                'button:has-text("Enter")'
            ];
            
            let enterDrawClicked = false;
            for (const selector of enterDrawSelectors) {
                this.log(`🎯 Trying selector: ${selector}`);
                
                // For Apply buttons, wait longer and check clickability more thoroughly
                if (selector.includes('Apply')) {
                    this.log(`Apply button detected - waiting for it to become clickable...`);
                    const applyButton = this.page.locator(selector).first();
                    
                    // Wait up to 30 seconds for Apply button to become clickable
                    let applyReady = false;
                    for (let i = 0; i < 30; i++) {
                        try {
                            if (await applyButton.isVisible({ timeout: 1000 }) && 
                                await applyButton.isEnabled({ timeout: 1000 })) {
                                this.log(`Apply button is now clickable after ${i + 1} seconds`);
                                applyReady = true;
                                break;
                            }
                        } catch (error) {
                            // Continue waiting
                        }
                        await this.page.waitForTimeout(1000);
                    }
                    
                    if (!applyReady) {
                        this.log(`⚠️ Apply button not clickable after 30 seconds, trying anyway...`);
                    }
                }
                
                enterDrawClicked = await this.humanInteractions.robustClick(selector, `FIFA entry button (${selector})`, null, 2, 60, this.log);
                if (enterDrawClicked) {
                    this.log(`Successfully clicked FIFA entry button with selector: ${selector}`);
                    break;
                }
            }
            
            if (!enterDrawClicked) {
                this.log('❌ All FIFA entry button selectors failed after 60 seconds - proxy may be blocked');
                this.log('🔍 Available selectors tried:');
                enterDrawSelectors.forEach((sel, idx) => this.log(`   ${idx + 1}. ${sel}`));
                throw new Error('Proxy appears to be blocked or too slow');
            }
            
            // Wait for page to update
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 4000));
            
            // Check current URL and page content to understand the flow
            const currentUrl = this.page.url();
            this.log(`📍 Current URL after first click: ${currentUrl}`);
            
            // Check if we're already at the credit card stage
            const hasAddCardButton = await this.page.locator('button:has-text("Add a new card")').count() > 0;
            const hasPaymentForm = await this.page.locator('iframe[src*="payment"]').count() > 0;
            
            this.log(`💳 Add card button present: ${hasAddCardButton}`);
            this.log(`💳 Payment iframe present: ${hasPaymentForm}`);
            
            if (hasAddCardButton || hasPaymentForm) {
                this.log('Already at credit card stage, skipping step 2');
                // Skip to credit card handling
                const creditCardResult = await this.handleCreditCardForm(this.currentUser);
                if (creditCardResult === 'RESTART_DRAW_ENTRY') {
                    this.log('🔄 Page reloaded during credit card handling - restarting from draw entry');
                    return 'RESTART_DRAW_ENTRY';
                }
                return;
            }
            
            // Check for Yes/No selection (appears after clicking Enter Draw)
            const hasYesNoContainer = await this.page.locator('.yes-no-container').count() > 0;
            const hasYesButton = await this.page.locator('button.yes-btn').count() > 0;
            
            this.log(`🎯 Yes/No container present: ${hasYesNoContainer}`);
            this.log(`🎯 Yes button present: ${hasYesButton}`);
            
            if (hasYesNoContainer || hasYesButton) {
                this.log('🎯 Found Yes/No selection, clicking Yes button...');
                
                // Step 2: Click the "Yes" button to enter the draw
                const yesButtonSelectors = [
                    'button.yes-btn',
                    'button:has-text("Enter the FIFA World Cup 26™ Presale Draw for Visa® Cardholders")',
                    '.yes-no-container button.yes-btn',
                    '.yes-no-container button:has-text("Enter the FIFA World Cup")'
                ];
                
                let yesClicked = false;
                for (const selector of yesButtonSelectors) {
                    this.log(`🎯 Trying Yes button selector: ${selector}`);
                    yesClicked = await this.humanInteractions.robustClick(selector, `Yes button (${selector})`, null, 2, 60, this.log);
                    if (yesClicked) {
                        this.log(`Successfully clicked Yes button with selector: ${selector}`);
                        break;
                    }
                }
                
                if (!yesClicked) {
                    this.log('❌ Failed to click Yes button, trying continue buttons as fallback...');
                }
            } else {
                this.log('ℹ️ No Yes/No selection found, looking for continue buttons...');
            }
            
            // Step 3: Look for Continue/Next button if still needed
            const continueSelectors = [
                'button:has-text("Continue")',
                'button:has-text("Next")', 
                'button:has-text("Proceed")',
                'button[aria-label="Continue"]',
                '.p-button:has-text("Continue")',
                '.stx-p-button:has-text("Continue")'
            ];
            
            let continueClicked = false;
            for (const selector of continueSelectors) {
                this.log(`🎯 Trying continue selector: ${selector}`);
                continueClicked = await this.humanInteractions.robustClick(selector, `Continue button (${selector})`, null, 2, 60, this.log);
                if (continueClicked) {
                    this.log(`Successfully clicked continue button with selector: ${selector}`);
                    break;
                }
            }
            
            if (!continueClicked) {
                this.log('⚠️ No continue button found, proceeding to credit card form...');
                // Might already be at the right stage, continue to credit card
            }
            
            // Wait for final processing
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 4000));
            
            // Handle credit card form
            const creditCardResult = await this.handleCreditCardForm(this.currentUser);
            if (creditCardResult === 'RESTART_DRAW_ENTRY') {
                this.log('🔄 Page reloaded during credit card handling - restarting from draw entry');
                return 'RESTART_DRAW_ENTRY';
            }
            
                this.log(`FIFA World Cup draw entry completed successfully on attempt ${attempt}!`);
                return; // Success, exit the retry loop
                
            } catch (error) {
                console.error(`❌ Error handling draw entry on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to handle draw entry after ${maxRetries} attempts`);
                    throw error;
                }
                
                // Wait before retry
                this.log(`Waiting 5 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 5000));
            }
        }
    }

    /**
     * Handle credit card form for FIFA World Cup entry
     */
    async handleCreditCardForm(user, maxRetries = 2) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`💳 Attempt ${attempt}/${maxRetries} - Looking for credit card form...`);
            
            // Check for CAPTCHA block first before checking for elements
            const isCaptchaBlocked = await this.checkForCaptchaBlock();
            if (isCaptchaBlocked) {
                this.log(`🤖 CAPTCHA/DataDome block detected while looking for credit card form - proxy/IP is blocked`);
                throw new Error('CAPTCHA_BLOCKED');
            }
            
            // Wait for page to load
            await this.page.waitForTimeout(UtilityHelper.randomDelay(3000, 5000));
            
            // First check if there's already a saved card
            const savedCardSelectors = [
                '.stx-card-alias-code-container',
                '.stx-card-alias.tw-flex.tw-justify-between',
                'div[role="button"][tabindex="0"][aria-controls*="manage-card"]'
            ];
            
            let savedCardFound = false;
            for (const selector of savedCardSelectors) {
                try {
                    const count = await this.page.locator(selector).count();
                    if (count > 0) {
                        this.log('💳 Found existing saved card, clicking to select it...');
                        const clicked = await this.humanInteractions.robustClick(selector, `Saved card (${selector})`, null, 2, 60, this.log);
                        if (clicked) {
                            savedCardFound = true;
                            
                            // Wait for the manage card panel to appear
                            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
                            
                            // Click "Make default" button
                            const makeDefaultSelectors = [
                                'button[aria-label="Make default"]',
                                'button:has-text("Make default")',
                                '.stx-lt-manage-card-alias-container button:has-text("Make default")'
                            ];
                            
                            let makeDefaultClicked = false;
                            for (const defaultSelector of makeDefaultSelectors) {
                                makeDefaultClicked = await this.humanInteractions.robustClick(defaultSelector, `"Make default" button (${defaultSelector})`, null, 2, 60, this.log);
                                if (makeDefaultClicked) {
                                    this.log('Clicked "Make default" button');
                                    break;
                                }
                            }
                            
                            if (!makeDefaultClicked) {
                                this.log('⚠️ "Make default" button not found, continuing...');
                            }
                            
                            // Wait a moment for the default selection to process
                            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
                            
                            // Skip to checkbox and submit
                            await this.acceptTermsAndSubmit();
                            return;
                        }
                    }
                } catch (error) {
                    // Continue to next selector
                }
            }
            
            if (!savedCardFound) {
                this.log('💳 No saved card found, proceeding to add new card...');
            }
            
            // Step 1: Click "Add a new card" button (wait up to 60 seconds)
            const addCardSelectors = [
                'button[aria-label="Add a new card"]',
                'button:has-text("Add a new card")',
                '.stx-card-alias-addCardBtn-container button'
            ];
            
            let addCardClicked = false;
            for (const selector of addCardSelectors) {
                addCardClicked = await this.humanInteractions.robustClick(selector, `"Add a new card" button (${selector})`, null, 2, 60, this.log);
                if (addCardClicked) {
                    break;
                }
            }
            
            if (!addCardClicked) {
                this.log('⚠️ "Add a new card" button not found after 60 seconds, may already be on form');
            }
            
            // Wait for iframe to appear and switch to it
            this.log('🔍 Looking for credit card iframe...');
            
            let iframe = null;
            let iframeFound = false;
            const maxIframeWait = 60; // 60 seconds for iframe
            let iframeAttempts = 0;
            
            while (!iframeFound && iframeAttempts < maxIframeWait) {
                iframeAttempts++;
                
                if (iframeAttempts % 10 === 0) {
                    this.log(`🔄 Looking for iframe... (${iframeAttempts}/${maxIframeWait} seconds)`);
                }
                
                try {
                    const iframes = await this.page.locator('iframe').all();
                    for (const frame of iframes) {
                        const src = await frame.getAttribute('src');
                        if (src && src.includes('payment-p8.secutix.com')) {
                            iframe = frame;
                            iframeFound = true;
                            this.log('Found payment iframe!');
                            break;
                        }
                    }
                } catch (error) {
                    // Continue waiting
                }
                
                if (!iframeFound) {
                    await this.page.waitForTimeout(1000);
                }
            }
            
            if (!iframeFound) {
                this.log('❌ Payment iframe not found after 60 seconds');
                throw new Error('Payment iframe not found - proxy may be blocked');
            }
            
            // Step 2: Use frameLocator approach for iframe interactions
            this.log('📝 Filling credit card form using frameLocator...');
            
            // Get the iframe src for frameLocator
            const iframeSrc = await iframe.getAttribute('src');
            this.log(`📍 Iframe src: ${iframeSrc}`);
            
            // Use frameLocator to interact with iframe elements
            const frameLocator = this.page.frameLocator('iframe[src*="payment-p8.secutix.com"]');
            
            // Fill card number (within iframe using frameLocator)
            const cardNumberSelectors = [
                'input[name="CardNumber"]',
                'input[name="cardNumber"]', 
                'input[name="card_number"]',
                'input[id*="card"]',
                'input[placeholder*="card"]'
            ];
            
            let cardFilled = false;
            for (const selector of cardNumberSelectors) {
                try {
                    this.log(`📝 Trying to fill card number with selector: ${selector}`);
                    const cardField = frameLocator.locator(selector).first();
                    
                    // Wait for field to be visible
                    await cardField.waitFor({ state: 'visible', timeout: 10000 });
                    
                    // Click and fill
                    await cardField.click();
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                    
                    // Clear and fill
                    await cardField.fill(''); // Clear first
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 400));
                    
                    // Type character by character for realism
                    for (let i = 0; i < user.CARD_NUM.length; i++) {
                        await cardField.type(user.CARD_NUM[i], { delay: UtilityHelper.randomDelay(80, 200) });
                    }
                    
                    this.log(`Card Number filled successfully with ${selector}`);
                    cardFilled = true;
                    break;
                    
                } catch (error) {
                    this.log(`⚠️ Failed to fill with ${selector}: ${error.message}`);
                    continue;
                }
            }
            
            if (!cardFilled) {
                throw new Error('Failed to fill card number with any selector after 60 seconds');
            }
            
            // Fill card holder name (within iframe using frameLocator)
            // Use generated address data for first and last name
            const firstName = this.generatedAddress ? this.generatedAddress.FIRST_NAME : user.FIRST_NAME;
            const lastName = this.generatedAddress ? this.generatedAddress.LAST_NAME : user.LAST_NAME;
            const fullName = `${firstName} ${lastName}`;
            
            this.log(`💳 Using cardholder name: ${fullName} (from ${this.generatedAddress ? 'generated address' : 'user data'})`);
            
            const holderSelectors = [
                'input[name="HolderName"]',
                'input[name="CardHolderName"]',
                'input[name="cardholder"]',
                'input[name="holder_name"]'
            ];
            
            let holderFilled = false;
            for (const selector of holderSelectors) {
                try {
                    this.log(`📝 Trying to fill cardholder name with selector: ${selector}`);
                    const holderField = frameLocator.locator(selector).first();
                    
                    await holderField.waitFor({ state: 'visible', timeout: 10000 });
                    await holderField.click();
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                    
                    await holderField.fill('');
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 400));
                    
                    // Type character by character
                    for (let i = 0; i < fullName.length; i++) {
                        await holderField.type(fullName[i], { delay: UtilityHelper.randomDelay(80, 200) });
                    }
                    
                    this.log(`Cardholder Name filled successfully: ${fullName}`);
                    holderFilled = true;
                    break;
                    
                } catch (error) {
                    this.log(`⚠️ Failed to fill cardholder with ${selector}: ${error.message}`);
                    continue;
                }
            }
            
            if (!holderFilled) {
                throw new Error('Failed to fill cardholder name after 60 seconds');
            }
            
            // Fill expiration month (within iframe using frameLocator)
            const monthSelectors = [
                'select[name="ExpMonth"]',
                'select[name="ExpirationMonth"]',
                'select[name="exp_month"]'
            ];
            
            let monthSelected = false;
            for (const selector of monthSelectors) {
                try {
                    this.log(`📝 Trying to select expiration month with selector: ${selector}`);
                    const monthField = frameLocator.locator(selector).first();
                    
                    await monthField.waitFor({ state: 'visible', timeout: 10000 });
                    await monthField.click();
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                    
                    // Use month from CSV, ensure it's zero-padded
                    const monthValue = user.EXPIRY_MONTH ? user.EXPIRY_MONTH.toString().padStart(2, '0') : '06';
                    await monthField.selectOption(monthValue);
                    
                    this.log(`Expiration Month selected successfully: ${monthValue}`);
                    monthSelected = true;
                    break;
                    
                } catch (error) {
                    this.log(`⚠️ Failed to select month with ${selector}: ${error.message}`);
                    continue;
                }
            }
            
            if (!monthSelected) {
                throw new Error('Failed to select expiration month after 60 seconds');
            }
            
            // Fill expiration year (within iframe using frameLocator)
            const yearSelectors = [
                'select[name="ExpYear"]',
                'select[name="ExpirationYear"]',
                'select[name="exp_year"]'
            ];
            
            let yearSelected = false;
            for (const selector of yearSelectors) {
                try {
                    this.log(`📝 Trying to select expiration year with selector: ${selector}`);
                    const yearField = frameLocator.locator(selector).first();
                    
                    await yearField.waitFor({ state: 'visible', timeout: 10000 });
                    await yearField.click();
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                    
                    // Use year from CSV
                    const yearValue = user.EXPIRY_YEAR ? user.EXPIRY_YEAR.toString() : '2028';
                    await yearField.selectOption(yearValue);
                    
                    this.log(`Expiration Year selected successfully: ${yearValue}`);
                    yearSelected = true;
                    break;
                    
                } catch (error) {
                    this.log(`⚠️ Failed to select year with ${selector}: ${error.message}`);
                    continue;
                }
            }
            
            if (!yearSelected) {
                throw new Error('Failed to select expiration year after 60 seconds');
            }
            
            // Fill CVV (within iframe using frameLocator)
            const cvvSelectors = [
                'input[name="VerificationCode"]',
                'input[name="CVV"]',
                'input[name="cvv"]',
                'input[name="cvc"]',
                'input[name="security_code"]'
            ];
            
            let cvvFilled = false;
            for (const selector of cvvSelectors) {
                try {
                    this.log(`📝 Trying to fill CVV with selector: ${selector}`);
                    const cvvField = frameLocator.locator(selector).first();
                    
                    await cvvField.waitFor({ state: 'visible', timeout: 10000 });
                    await cvvField.click();
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                    
                    await cvvField.fill('');
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 400));
                    
                    // Type character by character
                    for (let i = 0; i < user.CARD_CVV.length; i++) {
                        await cvvField.type(user.CARD_CVV[i], { delay: UtilityHelper.randomDelay(80, 200) });
                    }
                    
                    this.log(`CVV filled successfully`);
                    cvvFilled = true;
                    break;
                    
                } catch (error) {
                    this.log(`⚠️ Failed to fill CVV with ${selector}: ${error.message}`);
                    continue;
                }
            }
            
            if (!cvvFilled) {
                throw new Error('Failed to fill CVV after 60 seconds');
            }
            
            // Wait before submitting
            await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
            
            // Step 3: Click "Add now" button (within iframe using frameLocator)
            const addNowSelectors = [
                'button:has-text("Add now")',
                '.widgetPayNowButton',
                'button.widgetPayNowButton',
                '.sc-dIUggk button',
                'input[type="submit"]',
                'button[type="submit"]'
            ];
            
            let addNowClicked = false;
            for (const selector of addNowSelectors) {
                try {
                    this.log(`📝 Trying to click "Add now" with selector: ${selector}`);
                    const addNowButton = frameLocator.locator(selector).first();
                    
                    await addNowButton.waitFor({ state: 'visible', timeout: 10000 });
                    await addNowButton.click();
                    
                    this.log(`"Add now" button clicked successfully with ${selector}`);
                    addNowClicked = true;
                    break;
                    
                } catch (error) {
                    this.log(`⚠️ Failed to click "Add now" with ${selector}: ${error.message}`);
                    continue;
                }
            }
            
            if (!addNowClicked) {
                throw new Error('Failed to click "Add now" button after 60 seconds');
            }
            
            this.log('🔄 Switching back to main page for terms and conditions...');
            
            // Wait longer for card to be fully processed and page to update
            this.log('Waiting for credit card to be processed and page to update...');
            await this.page.waitForTimeout(UtilityHelper.randomDelay(5000, 8000));
            
            // Wait for the terms checkbox to become available and clickable
            this.log('🔍 Waiting for terms and conditions checkbox to become available...');
            
            // Debug: Check what checkboxes are currently on the page
            try {
                const allCheckboxes = await this.page.locator('input[type="checkbox"]').all();
                this.log(`🔍 Found ${allCheckboxes.length} checkboxes on the page`);
                for (let i = 0; i < allCheckboxes.length; i++) {
                    const id = await allCheckboxes[i].getAttribute('id');
                    const className = await allCheckboxes[i].getAttribute('class');
                    const ariaLabel = await allCheckboxes[i].getAttribute('aria-label');
                    this.log(`   Checkbox ${i + 1}: id="${id}", class="${className}", aria-label="${ariaLabel}"`);
                }
            } catch (error) {
                this.log(`⚠️ Error debugging checkboxes: ${error.message}`);
            }
            
            const termsCheckboxReady = await this.waitForTermsCheckboxReady();
            if (!termsCheckboxReady) {
                this.log('⚠️ Terms checkbox not ready after waiting - checking if we need to return to draw entry...');
                
                // Check if we're back on the main FIFA page (terms checkbox not found usually means page refreshed)
                const currentUrl = this.page.url();
                if (currentUrl.includes('fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications') || 
                    currentUrl.includes('fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications')) {
                    this.log('🔄 Detected return to main FIFA page - terms checkbox not found, returning to draw entry flow');
                    return 'RESTART_DRAW_ENTRY';
                }
                
                this.log('⚠️ Terms checkbox not ready, but continuing...');
            }
            
            // Step 4: Check terms and conditions with enhanced verification
            const termsSelectors = [
                'input[id="stx-confirmation-terms-and-conditions"]',
                '.p-checkbox-input',
                'input[type="checkbox"][required]',
                '.stx-confirmation-terms-and-conditions input[type="checkbox"]'
            ];
            
            let termsChecked = false;
            for (const selector of termsSelectors) {
                const result = await this.clickTermsCheckboxWithVerification(selector);
                if (result === 'RESTART_DRAW_ENTRY') {
                    this.log('🔄 Page reloaded during checkbox detection - restarting from draw entry');
                    return 'RESTART_DRAW_ENTRY';
                }
                if (result) {
                    termsChecked = true;
                    break;
                }
            }
            
            if (!termsChecked) {
                this.log('❌ All terms and conditions selectors failed - checking if we need to return to draw entry...');
                
                // Check if we're back on the main FIFA page (terms checkbox not found usually means page refreshed)
                const currentUrl = this.page.url();
                if (currentUrl.includes('fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets') || 
                    currentUrl.includes('fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications')) {
                    this.log('🔄 Detected return to main FIFA page - terms checkbox not found, returning to draw entry flow');
                    return 'RESTART_DRAW_ENTRY';
                }
                
                this.log('❌ All terms and conditions selectors failed after 60 seconds - proxy may be blocked');
                throw new Error('Proxy appears to be blocked or too slow');
            }
            
            // Wait for terms checkbox to be fully processed before submit
            this.log('Waiting for terms checkbox to be fully processed...');
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
            
            // Verify terms checkbox is still checked before proceeding
            const termsStillChecked = await this.verifyTermsCheckboxChecked();
            if (!termsStillChecked) {
                this.log('⚠️ Terms checkbox not properly checked, attempting to fix...');
                const fixed = await this.clickTermsCheckboxWithVerification('input[id="stx-confirmation-terms-and-conditions"]');
                if (!fixed) {
                    this.log('❌ Could not fix terms checkbox, proceeding anyway...');
                }
            }
            
            // Step 5: Click "Submit Entry" or "Confirm Application" button (back on main page)
            const submitSelectors = [
                'button[aria-label="Submit Entry"]',               // Primary - matches your HTML!
                'button:has-text("Submit Entry")',                // Text match
                '.stx-p-button:has-text("Submit Entry")',         // With class
                'button[aria-label="Confirm Application"]',       // Alternative
                'button:has-text("Confirm Application")',         // Alternative text
                '.stx-p-button:has-text("Confirm Application")',  // Alternative with class
                // Additional fallbacks
                'button:has-text("Submit")',
                'button:has-text("Confirm")',
                '.p-button:has-text("Submit")',
                '.p-button:has-text("Confirm")'
            ];
            
            let submitClicked = false;
            for (const selector of submitSelectors) {
                submitClicked = await this.humanInteractions.robustClick(selector, `"Submit Entry" button (${selector})`, null, 2, 60, this.log);
                if (submitClicked) {
                    break;
                }
            }
            
            if (!submitClicked) {
                this.log('❌ All "Submit Entry" button selectors failed after 60 seconds - proxy may be blocked');
                throw new Error('Proxy appears to be blocked or too slow');
            }
            
            // Wait for final submission
            await this.page.waitForTimeout(UtilityHelper.randomDelay(3000, 5000));
            
                this.log(`Credit card form completed successfully on attempt ${attempt}!`);
                return; // Success, exit the retry loop
                
            } catch (error) {
                console.error(`❌ Error handling credit card form on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to handle credit card form after ${maxRetries} attempts`);
                    throw error;
                }
                
                // Wait before retry
                this.log(`Waiting 5 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 5000));
            }
        }
    }

    /**
     * Wait for terms checkbox to become ready and clickable
     * @returns {boolean} True if checkbox is ready, false if timeout
     */
    async waitForTermsCheckboxReady() {
        try {
            this.log('🔍 Waiting for terms checkbox to be ready...');
            
            const maxAttempts = 30; // 30 seconds
            let attempts = 0;
            
            while (attempts < maxAttempts) {
                attempts++;

                const isCaptchaBlocked = await this.checkForCaptchaBlock();
                if (isCaptchaBlocked) {
                    this.log(`🤖 CAPTCHA/DataDome block detected - proxy/IP is blocked`);
                    throw new Error('CAPTCHA_BLOCKED');
                }
                
                if (attempts % 5 === 0) {
                    this.log(`🔄 Checking terms checkbox readiness... (${attempts}/${maxAttempts} seconds)`);
                    
                    // Debug: Check what's actually on the page
                    try {
                        const currentUrl = this.page.url();
                        this.log(`📍 Current URL: ${currentUrl}`);
                        
                        // Check if the container exists
                        const containerExists = await this.page.locator('.stx-confirmation-terms-and-conditions').count();
                        this.log(`📦 Terms container exists: ${containerExists > 0}`);
                        
                        // Check all checkboxes on the page
                        const allCheckboxes = await this.page.locator('input[type="checkbox"]').count();
                        this.log(`☑️ Total checkboxes on page: ${allCheckboxes}`);
                        
                        // Check specific selectors
                        const specificId = await this.page.locator('#stx-confirmation-terms-and-conditions').count();
                        this.log(`🎯 Specific ID checkbox count: ${specificId}`);
                        
                        // List all checkbox IDs and classes
                        const checkboxInfo = await this.page.evaluate(() => {
                            const checkboxes = document.querySelectorAll('input[type="checkbox"]');
                            return Array.from(checkboxes).map(cb => ({
                                id: cb.id,
                                className: cb.className,
                                ariaLabel: cb.getAttribute('aria-label'),
                                required: cb.hasAttribute('required')
                            }));
                        });
                        this.log(`📋 All checkboxes:`, checkboxInfo);
                        
                    } catch (debugError) {
                        this.log(`⚠️ Debug error: ${debugError.message}`);
                    }
                }
                
                try {
                    // Check multiple checkbox selectors directly (no container required)
                    const checkboxSelectors = [
                        'input[id="stx-confirmation-terms-and-conditions"]',
                        '#stx-confirmation-terms-and-conditions',
                        '.p-checkbox-input',
                        'input[type="checkbox"][required]',
                        'input[type="checkbox"][aria-label*="terms"]',
                        'input[type="checkbox"][aria-label*="conditions"]'
                    ];
                    
                    for (const selector of checkboxSelectors) {
                        try {
                            const checkbox = this.page.locator(selector);
                            const count = await checkbox.count();
                            this.log(`🔍 Selector "${selector}": count=${count}`);
                            
                            if (count > 0) {
                                const isVisible = await checkbox.isVisible({ timeout: 1000 });
                                const isEnabled = await checkbox.isEnabled({ timeout: 1000 });
                                
                                this.log(`🔍 Selector "${selector}": visible=${isVisible}, enabled=${isEnabled}`);
                                
                                if (isVisible && isEnabled) {
                                    this.log(`Terms checkbox is ready and clickable (found with: ${selector})`);
                                    return true;
                                }
                            }
                        } catch (selectorError) {
                            this.log(`⚠️ Selector "${selector}" error: ${selectorError.message}`);
                        }
                    }
                } catch (error) {
                    this.log(`⚠️ Error checking selectors: ${error.message}`);
                }
                
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            this.log('⚠️ Terms checkbox not ready after 30 seconds');
            return false;
            
        } catch (error) {
            this.log(`⚠️ Error waiting for terms checkbox: ${error.message}`);
            return false;
        }
    }

    /**
     * Click terms checkbox with enhanced verification
     * @param {string} selector - CSS selector for the checkbox
     * @returns {boolean} True if successfully clicked and verified, false otherwise
     */
    async clickTermsCheckboxWithVerification(selector) {
        try {
            this.log(`🎯 Attempting to click terms checkbox: ${selector}`);
            
            // First, wait for the element to be visible and clickable
            const found = await this.humanInteractions.waitForElementRobust(selector, 'Terms checkbox', null, 60, this.log);
            if (found === 'RESTART_DRAW_ENTRY') {
                this.log('🔄 Page reloaded and returned to main FIFA page - restarting from draw entry');
                return 'RESTART_DRAW_ENTRY';
            }
            if (!found) {
                this.log(`❌ Terms checkbox not found: ${selector}`);
                return false;
            }
            
            // Check if already checked
            const checkbox = this.page.locator(selector).first();
            const isAlreadyChecked = await checkbox.isChecked();
            
            if (isAlreadyChecked) {
                this.log('Terms checkbox is already checked');
                return true;
            }
            
            // Scroll the checkbox into view
            await checkbox.scrollIntoViewIfNeeded();
            await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
            
            // Click the checkbox
            this.log('🖱️ Clicking terms checkbox...');
            await this.humanInteractions.humanClick(selector);
            
            // Wait for the click to register
            await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
            
            // Verify the checkbox was actually checked
            const isCheckedAfterClick = await checkbox.isChecked();
            
            if (isCheckedAfterClick) {
                this.log('Terms checkbox successfully checked and verified');
                return true;
            } else {
                this.log('⚠️ Terms checkbox click did not register, trying again...');
                
                // Try clicking again with different approach
                await checkbox.click({ force: true });
                await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
                
                // Verify again
                const isCheckedAfterRetry = await checkbox.isChecked();
                if (isCheckedAfterRetry) {
                    this.log('Terms checkbox checked on retry');
                    return true;
                } else {
                    this.log('❌ Terms checkbox still not checked after retry');
                    return false;
                }
            }
            
        } catch (error) {
            this.log(`❌ Error clicking terms checkbox: ${error.message}`);
            return false;
        }
    }

    /**
     * Verify that the terms checkbox is properly checked
     * @returns {boolean} True if checked, false otherwise
     */
    async verifyTermsCheckboxChecked() {
        try {
            const checkbox = this.page.locator('input[id="stx-confirmation-terms-and-conditions"]');
            const isChecked = await checkbox.isChecked();
            
            if (isChecked) {
                this.log('Terms checkbox verification: CHECKED');
                return true;
            } else {
                this.log('❌ Terms checkbox verification: NOT CHECKED');
                return false;
            }
        } catch (error) {
            this.log(`⚠️ Error verifying terms checkbox: ${error.message}`);
            return false;
        }
    }

    /**
     * Fill credit card field with realistic typing
     */
    async fillCreditCardField(selector, value, fieldName) {
        try {
            this.log(`📝 Filling ${fieldName}...`);
            
            const field = this.page.locator(selector).first();
            if (await field.isVisible({ timeout: 3000 })) {
                await this.humanInteractions.humanClick(selector);
                await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 500));
                
                // Clear field
                await field.selectText();
                await field.press('Delete');
                await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 400));
                
                // Type with realistic delays
                for (let i = 0; i < value.length; i++) {
                    const char = value[i];
                    await field.type(char, { delay: UtilityHelper.randomDelay(80, 200) });
                    
                    // Occasional pause
                    if (Math.random() < 0.1) {
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 500));
                    }
                }
                
                // Trigger events
                await field.dispatchEvent('input');
                await field.dispatchEvent('change');
                await field.dispatchEvent('blur');
                
                this.log(`${fieldName} filled successfully`);
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
            } else {
                this.log(`⚠️ ${fieldName} field not found`);
            }
        } catch (error) {
            this.log(`⚠️ Error filling ${fieldName}: ${error.message}`);
        }
    }

    /**
     * Select option from dropdown with realistic clicking
     */
    async selectCreditCardDropdown(selector, value, fieldName) {
        try {
            this.log(`📝 Selecting ${fieldName}...`);
            
            const dropdown = this.page.locator(selector).first();
            if (await dropdown.isVisible({ timeout: 3000 })) {
                // Click dropdown to open
                await this.humanInteractions.humanClick(selector);
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                
                // Select option
                await dropdown.selectOption(value);
                
                // Trigger events
                await dropdown.dispatchEvent('change');
                await dropdown.dispatchEvent('blur');
                
                this.log(`${fieldName} selected: ${value}`);
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
            } else {
                this.log(`⚠️ ${fieldName} dropdown not found`);
            }
        } catch (error) {
            this.log(`⚠️ Error selecting ${fieldName}: ${error.message}`);
        }
    }

    /**
     * Check age confirmation checkbox with verification
     */
    async checkAgeConfirmation() {
        try {
            this.log('🔘 Checking age confirmation...');
            
            const checkboxSelectors = [
                'input[name="contactCriteria[AGEVAL].values[0]"]',
                'input[id*="AGEVAL"]',
                'input[value="true"][type="checkbox"]'
            ];
            
            let checkboxChecked = false;
            for (const selector of checkboxSelectors) {
                try {
                    const checkbox = this.page.locator(selector).first();
                    if (await checkbox.isVisible({ timeout: 3000 })) {
                        this.log(`Found age checkbox with selector: ${selector}`);
                        
                        // Click the checkbox
                        await this.humanInteractions.humanClick(selector);
                        await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(500, 1000)));
                        
                        // Verify it's actually checked using JavaScript
                        const isChecked = await this.page.evaluate((sel) => {
                            const cb = document.querySelector(sel);
                            return cb ? cb.checked : false;
                        }, selector);
                        
                        this.log(`🔍 Age checkbox verification: checked = ${isChecked}`);
                        
                        if (isChecked) {
                            checkboxChecked = true;
                            this.log('Age confirmation successfully checked and verified');
                            break;
                        } else {
                            this.log('⚠️ Checkbox not checked, trying click again...');
                            await this.humanInteractions.humanClick(selector);
                            await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(500, 1000)));
                            
                            // Check again
                            const recheckResult = await this.page.evaluate((sel) => {
                                const cb = document.querySelector(sel);
                                return cb ? cb.checked : false;
                            }, selector);
                            
                            if (recheckResult) {
                                checkboxChecked = true;
                                this.log('Age confirmation checked on retry');
                                break;
                            }
                        }
                    }
                } catch (error) {
                    continue;
                }
            }
            
            if (!checkboxChecked) {
                this.log('⚠️ Age confirmation checkbox not found or could not be checked');
            }
            
        } catch (error) {
            this.log(`⚠️ Error checking age confirmation: ${error.message}`);
        }
    }

    /**
     * Select all tournament rounds
     */
    async selectTournamentRounds() {
        try {
            this.log('🏆 Selecting tournament rounds...');
            
            const rounds = [
                'input[value="GS"]', // Group Stage
                'input[value="R32"]', // Round of 32
                'input[value="r16"]', // Round of 16
                'input[value="QF"]', // Quarter Final
                'input[value="SF"]', // Semi Final
                'input[value="FINAL"]' // Final
            ];
            
            for (const roundSelector of rounds) {
                try {
                    const checkbox = this.page.locator(roundSelector);
                    if (await checkbox.isVisible({ timeout: 2000 })) {
                        await this.humanInteractions.humanClick(roundSelector);
                        this.log(`Selected: ${roundSelector}`);
                    }
                } catch (error) {
                    continue;
                }
            }
            
            this.log('Tournament rounds selected');
        } catch (error) {
            this.log(`⚠️ Error selecting tournament rounds: ${error.message}`);
        }
    }

    /**
     * Select fan country (Netherlands)
     */
    async selectFanCountry() {
        try {
            this.log('🇳🇱 Selecting fan country (Netherlands)...');
            
            const select = this.page.locator('select[name="contactCriteria[FanOF26].values[0]"]');
            if (await select.isVisible({ timeout: 5000 })) {
                await this.humanInteractions.humanClick('select[name="contactCriteria[FanOF26].values[0]"]');
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                await select.selectOption('NED'); // Netherlands
                this.log('Fan country selected: Netherlands');
            } else {
                this.log('⚠️ Fan country select not found');
            }
        } catch (error) {
            this.log(`⚠️ Error selecting fan country: ${error.message}`);
        }
    }

    /**
     * Select random 4 venues
     */
    async selectRandomVenues() {
        try {
            this.log('🏟️ Selecting random 4 venues...');
            
            const venues = [
                'ATL', 'BST', 'DAL', 'HOU', 'KC', 'LA', 'MIA', 
                'NY/NJ', 'PHI', 'SF/BA', 'SEA', 'VAN', 'TOR', 
                'GUA', 'MEX', 'MON'
            ];
            
            // Shuffle and take 4
            const shuffled = venues.sort(() => 0.5 - Math.random());
            const selectedVenues = shuffled.slice(0, 4);
            
            this.log(`Selected venues: ${selectedVenues.join(', ')}`);
            
            const select = this.page.locator('select[name="contactCriteria[VENUE].values"]');
            if (await select.isVisible({ timeout: 5000 })) {
                await this.humanInteractions.humanClick('select[name="contactCriteria[VENUE].values"]');
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                for (const venue of selectedVenues) {
                    await select.selectOption({ value: venue });
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 400));
                }
                this.log('Random venues selected');
            } else {
                this.log('⚠️ Venue select not found');
            }
        } catch (error) {
            this.log(`⚠️ Error selecting venues: ${error.message}`);
        }
    }

    /**
     * Fill address information
     */
    async fillAddressInfo(user) {
        try {
            this.log('🏠 Filling address information...');
            
            // Fill street address
            const streetSelector = 'input[name*="street"], input[name*="address"]';
            const streetField = this.page.locator(streetSelector).first();
            if (await streetField.isVisible({ timeout: 5000 })) {
                await this.humanInteractions.fillFieldRealistically(streetSelector, user.STREET_AND_NUMBER, 'Street address', null, this.log);
            }
            
            // Fill postal code
            const postalSelector = 'input[name*="postal"], input[name*="zip"]';
            const postalField = this.page.locator(postalSelector).first();
            if (await postalField.isVisible({ timeout: 5000 })) {
                await this.humanInteractions.fillFieldRealistically(postalSelector, user.POSTALCODE, 'Postal code', null, this.log);
            }
            
            // Fill city from CSV
            const citySelector = 'input[name*="city"], input[name*="town"]';
            const cityField = this.page.locator(citySelector).first();
            if (await cityField.isVisible({ timeout: 5000 })) {
                const cityValue = user.CITY || 'Amsterdam'; // Fallback to Amsterdam if not specified
                await this.humanInteractions.fillFieldRealistically(citySelector, cityValue, 'City', null, this.log);
            }
            
        } catch (error) {
            this.log(`⚠️ Error filling address info: ${error.message}`);
        }
    }

    /**
     * Fill phone number with NL country code
     */
    async fillPhoneNumber(user) {
        try {
            this.log('📞 Filling phone number...');
            
            // Use generated phone number (prioritize generated over CSV)
            const phoneNumber = this.generatedAddress?.PHONE_NUMBER || user.PHONE_NUMBER || '0612345678';
            this.log(`📱 Using phone number: ${phoneNumber}`);
            
            // Determine country code based on phone format
            let countryCode = '31'; // Default to Netherlands
            let cleanPhoneNumber = phoneNumber;
            
            if (phoneNumber && phoneNumber.startsWith('+1')) {
                countryCode = '1'; // USA
                cleanPhoneNumber = phoneNumber.replace(/^\+1/, '');
            } else if (phoneNumber && phoneNumber.startsWith('+52')) {
                countryCode = '52'; // Mexico
                cleanPhoneNumber = phoneNumber.replace(/^\+52\s*/, '').replace(/\s/g, '');
            } else if (phoneNumber && phoneNumber.startsWith('06')) {
                countryCode = '31'; // Netherlands
                cleanPhoneNumber = phoneNumber;
            } else if (phoneNumber) {
                // Remove any existing country codes
                cleanPhoneNumber = phoneNumber.replace(/^\+31/, '').replace(/^31/, '');
            } else {
                // Fallback if phoneNumber is undefined
                cleanPhoneNumber = '0612345678';
            }
            
            // 1. Select country code from dropdown
            const countrySelect = this.page.locator('select[name="phonePrefix"], select[id="phone_prefix"]');
            if (await countrySelect.isVisible({ timeout: 5000 })) {
                await this.humanInteractions.humanClick('select[name="phonePrefix"], select[id="phone_prefix"]');
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                await countrySelect.selectOption(countryCode);
                this.log(`Country code selected: +${countryCode}`);
                await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
            } else {
                this.log('⚠️ Country code select not found');
            }
            
            // 2. Fill phone number field (without country code)
            const phoneField = this.page.locator('input[name*="phone"], input[type="tel"]').first();
            if (await phoneField.isVisible({ timeout: 5000 })) {
                // Clear field first
                await this.humanInteractions.humanClick('input[name*="phone"], input[type="tel"]');
                await phoneField.selectText();
                await phoneField.press('Delete');
                await this.page.waitForTimeout(UtilityHelper.randomDelay(200, 500));
                
                // Type phone number character by character
                await phoneField.type(cleanPhoneNumber, { delay: UtilityHelper.randomDelay(100, 200) });
                
                // Verify the phone number was filled correctly
                const filledValue = await phoneField.inputValue();
                this.log(`Phone number filled: ${filledValue} (with +${countryCode} country code)`);
            } else {
                this.log('⚠️ Phone number field not found');
            }
        } catch (error) {
            this.log(`⚠️ Error filling phone number: ${error.message}`);
        }
    }

    /**
     * Submit the account completion form
     */
    async submitAccountForm() {
        try {
            this.log('📤 Submitting account form...');
            
            // Look for submit button (including Save button)
            const submitSelectors = [
                'a[id="save"]', // Save button specific selector
                'span[id="saveButton"] a',
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Continue")',
                'button:has-text("Complete")',
                'button:has-text("Save")',
                '.btn-primary'
            ];
            
            let submitted = false;
            for (const selector of submitSelectors) {
                submitted = await this.humanInteractions.robustClick(selector, `Submit/Save button (${selector})`, null, 2, 60, this.log);
                if (submitted) {
                    break;
                }
            }
            
            if (!submitted) {
                this.log('❌ All submit button selectors failed after 60 seconds');
                
                // Try JavaScript click as fallback
                this.log('🔍 Trying JavaScript click on Save button...');
                const jsClicked = await this.page.evaluate(() => {
                    const saveLink = document.querySelector('a[id="save"]');
                    if (saveLink) {
                        saveLink.click();
                        return true;
                    }
                    
                    // Try onclick function directly
                    if (typeof account !== 'undefined' && account.register && account.register.submitRegisterForm) {
                        account.register.submitRegisterForm(false, false, true, true, false, getFormConfigMap(), 38, true);
                        return true;
                    }
                    
                    return false;
                });
                
                if (jsClicked) {
                    submitted = true;
                    this.log('Form submitted via JavaScript');
                } else {
                    this.log('❌ JavaScript submit also failed');
                }
            }
            
            // Wait after submission
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 4000));
            
        } catch (error) {
            this.log(`⚠️ Error submitting form: ${error.message}`);
        }
    }


    async checkForCaptchaBlock() {
        try {
            // Only use Method 2: Check for specific geo.captcha-delivery.com/captcha/ iframe
            const iframes = await this.page.locator('iframe').all();
            for (const iframe of iframes) {
                try {
                    const src = await iframe.getAttribute('src');
                    if (src && (src.includes('https://geo.captcha-delivery.com/interstitial/') || src.includes('https://geo.captcha-delivery.com/captcha/'))) {
                        this.log(`❌ Captcha block detected via iframe: ${src}`);
                        this.log(`🛑 Stopping browser immediately due to captcha detection...`);
                        
                        // Immediately stop the browser
                        await this.close();
                        this.stop();
                        
                        return true;
                    }
                } catch (error) {
                    // Continue checking other iframes
                }
            }

            return false;
        } catch (error) {
            this.log(`⚠️ Error checking for captcha block: ${error.message}`);
            return false;
        }
    }

    async markAccountAsCreated(user){
        this.log('💾 Updating CSV: marking account as created...');
        const csvHelper = new CsvHelper();
        await csvHelper.readCsvData();
        const accountUpdated = await csvHelper.markAccountCreated(user.EMAIL);
        if (accountUpdated) {
            this.log('CSV updated: HAS_ACCOUNT = TRUE');
        } else {
            this.log('⚠️ Failed to update CSV for account creation');
        }
        
        // Mark that account was created in this session
        user.accountCreatedInThisSession = true;
    }

    /**
     * Clean phone number for form input (remove country code)
     */
    cleanPhoneNumberForForm(phoneNumber) {
        return UtilityHelper.cleanPhoneNumberForForm(phoneNumber);
    }


    async runCompleteFifaProcess(user, taskNumber, proxies, startUrl = 'https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets') {
        try {
            // Set task number, user, and proxies
            this.taskNumber = taskNumber;
            this.currentUser = user;
            this.proxies= proxies;
            
            
            // Step 1: Create and start profile
            const profileResult = await this.createAndStartProfile();
            if (profileResult === 'NO_PROXIES_AVAILABLE') {
                this.log('❌ No unused proxies available - stopping processing', 'error');
                return 'NO_PROXIES_AVAILABLE';
            }
            if (!profileResult) {
                throw new Error('Failed to create and start profile');
            }
            
            // Step 2: Initialize browser
            await this.initialize();
            
            // Step 3: Run FIFA automation
            const result = await this.startFifaAutomation(startUrl, taskNumber - 1); // Convert to 0-based for compatibility
            
            // Step 4: Cleanup profile
            await this.deleteProfile();
            
            return result;
            
        } catch (error) {
            this.log(`❌ Error in complete FIFA process: ${error.message}`, 'error');
            
            // Always cleanup on error
            try {
                await this.deleteProfile();
            } catch (cleanupError) {
                this.log(`⚠️ Error during cleanup: ${cleanupError.message}`, 'warn');
            }
            
            throw error;
        }
    }

    async startFifaAutomation(startUrl = 'https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets', userIndex = null) {
        try {
            this.isRunning = true;
            
            // Set task number from userIndex parameter (convert 0-based to 1-based)
            this.taskNumber = userIndex !== null ? userIndex + 1 : 1;
            
            this.log(`🌐 Navigating to: ${startUrl}`);

            // Load user data first
            const user = await this.loadUserData(userIndex);
            if (!user) {
                throw new Error('Failed to load user data');
            }

            // Navigate to the page with increased timeout and network error handling
            this.log('🌐 Navigating to FIFA tickets page...');
            let navigationSuccess = false;
            let retryCount = 0;
            const maxRetries = 3;
            await this.page.goto(startUrl, { 
                waitUntil: 'networkidle',
                timeout: 30000  // Increased to 60 seconds
            });
           
            
            while (!navigationSuccess && retryCount < maxRetries) {
                try {
                    await this.page.goto(startUrl, { 
                        waitUntil: 'networkidle',
                        timeout: 60000  // Increased to 60 seconds
                    });
                    this.log('Page loaded successfully');
                    navigationSuccess = true;
                } catch (error) {
                    retryCount++;
                    
                    // Check for specific network errors that require page refresh
                    if (error.message.includes('ERR_EMPTY_RESPONSE') || 
                        error.message.includes('ERR_CONNECTION_CLOSED') ||
                        error.message.includes('ERR_TIMED_OUT') ||
                        error.message.includes('net::ERR_') ||
                        error.message.includes('Navigation timeout') ||
                        error.message.includes('Protocol error') ||
                        error.message.includes('Target closed') ||
                        error.message.includes('Execution context was destroyed')) {
                        
                        this.log(`🔄 Network error detected during navigation: ${error.message} - retrying (${retryCount}/${maxRetries})...`);
                        
                        if (retryCount < maxRetries) {
                            // Wait a bit before retrying
                            await this.page.waitForTimeout(3000);
                            continue;
                        }
                    } else if (error.message.includes('Timeout')) {
                        this.log('⚠️ Page load timeout, trying with domcontentloaded...');
                        try {
                            await this.page.goto(startUrl, { 
                                waitUntil: 'domcontentloaded',
                                timeout: 60000 
                            });
                            this.log('Page loaded with domcontentloaded');
                            navigationSuccess = true;
                        } catch (retryError) {
                            if (retryCount < maxRetries) {
                                this.log(`⚠️ domcontentloaded also failed, retrying (${retryCount}/${maxRetries})...`);
                                await this.page.waitForTimeout(3000);
                                continue;
                            } else {
                                throw retryError;
                            }
                        }
                    } else {
                        throw error;
                    }
                }
            }
            
            if (!navigationSuccess) {
                throw new Error(`Failed to navigate to FIFA page after ${maxRetries} attempts`);
            }

            // Wait for page to fully load
            await this.waitForPageLoad();

            // Check for browser error pages after navigation
            if (await this.humanInteractions.detectErrorPage()) {
                this.log(`🔄 Browser error page detected after navigation - refreshing page...`);
                try {
                    await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                    await this.page.waitForTimeout(3000);
                    this.log('Page refreshed successfully after error page detection');
                } catch (reloadError) {
                    this.log(`⚠️ Page reload failed after error page detection: ${reloadError.message}`);
                    throw new Error('NAVIGATION_ERROR_PAGE_DETECTED');
                }
            }

            // Click Learn more button
            const learnMoreClicked = await this.clickLearnMoreButton();
            if (!learnMoreClicked) {
                throw new Error('Failed to click Learn more button');
            }

            // Wait for navigation or new tab
            this.log('Waiting for navigation...');
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 5000));

            // Check if we're on a new page
            const currentUrl = this.page.url();
            this.log(`📍 Current URL: ${currentUrl}`);

            // Check if we are blocked by CAPTCHA/DataDome (enhanced detection)
            const isCaptchaBlocked = await this.checkForCaptchaBlock();
            if (isCaptchaBlocked) {
                this.log('❌ CAPTCHA/DataDome block detected - proxy flagged');
                throw new Error('CAPTCHA_BLOCKED');
            }


            // Handle new tab/window if opened
            const pages = this.context.pages();
            if (pages.length > 1) {
                this.log(`🔄 New tab detected! Switching to new tab (${pages.length} tabs total)`);
                
                // Switch to the new tab (usually the last one)
                const newPage = pages[pages.length - 1];
                this.page = newPage;
                
                const newUrl = this.page.url();
                this.log(`📍 Switched to new tab URL: ${newUrl}`);
            }

            // Wait for new tab to open with auth.fifa.com
            this.log('Waiting for new tab with auth.fifa.com...');
            await this.waitForNewTabWithAuth();

            // Check if user is already logged in (skip cookie banner and login if so)
            const isAlreadyLoggedIn = await this.checkIfAlreadyLoggedIn();
            
            if (isAlreadyLoggedIn) {
                this.log('User is already logged in, skipping cookie banner and login steps');
                
                // Check if account completion is needed before proceeding to draw entry
                const needsAccountCompletion = await this.checkIfAccountCompletionNeeded();
                
                if (needsAccountCompletion) {
                    this.log('📝 Account completion needed, handling personal details first...');
                    await this.handleAccountCompletion(user);
                    return true; // handleAccountCompletion already handles draw entry and webhook
                } else {
                    this.log('Account already completed, proceeding directly to draw entry...');
                    const drawEntryResult = await this.handleDrawEntry(user);
                    if (drawEntryResult === 'RESTART_DRAW_ENTRY') {
                        this.log('🔄 Page reloaded during draw entry - restarting from draw entry');
                        await this.handleDrawEntry(user);
                    }
                    
                    // After draw entry, handle completion and webhook
                    await this.handleCompletionAndWebhook(user);
                }
                
                return true;
            }

            // Handle cookie banner on the new page (only for non-logged-in users)
            await this.waitForPageWithCookieBanner();

            // Check if user has account or needs to register
            const hasAccount = ImapHelper.hasAccount(user);
            this.log(`🔐 User has account: ${hasAccount}`);
            
            if (hasAccount) {
                // Fill login form with user data (robust methods)
                const loginFilled = await this.fillLoginFormRobust(user);
                if (!loginFilled) {
                    throw new Error('Failed to fill login form after 60 seconds - proxy may be blocked');
                }

                // Ensure cookie banner is not blocking before login
                await this.ensureCookieBannerNotBlocking();
                
                // Click login button (robust method)
                const loginClicked =  await this.humanInteractions.clickLoginButtonRobust();
                if (!loginClicked) {
                    throw new Error('Failed to click login button after 60 seconds - proxy may be blocked');
                }
                
                const loginResult = await this.handleLoginResult();
                
                if (loginResult === 'EMAIL_VERIFICATION_NEEDED') {
                    this.log('📧 Email verification needed after login (user exists case), handling OTP verification...');
                    await this.handleEmailVerification(user);
                    
                    // After email verification, check what's needed next
                    const needsAccountCompletion = await this.checkIfAccountCompletionNeeded();
                    if (needsAccountCompletion) {
                        this.log('📝 Account completion needed after email verification (user exists case)...');
                        await this.handleAccountCompletion(user);
                        return true; // handleAccountCompletion already handles draw entry and webhook
                    }
                    
                    // Proceed to draw entry
                    const drawEntryResult = await this.handleDrawEntry();
                    if (drawEntryResult === 'RESTART_DRAW_ENTRY') {
                        this.log('🔄 Page reloaded during draw entry - restarting from draw entry');
                        await this.handleDrawEntry();
                    }
                    await this.handleCompletionAndWebhook(user);
                    return true;
                    
                } else if(loginResult === 'ACCOUNT_COMPLETION_NEEDED') {
                    this.log('📝 Account completion needed after login...');
                    await this.handleAccountCompletion(user);
                    return true; // handleAccountCompletion already handles draw entry and webhook
                }else if(loginResult === 'DRAW_ENTRY_NEEDED'){
                    // wait till page loaded
                    await this.page.waitForLoadState('domcontentloaded', { timeout: 30000 });
                    const completionDetected = await this.detectCompletionPage();
                    if (completionDetected) {
                        this.log('🎉 Entry completion page detected!');
                        const accountWasCreated = user && user.accountCreatedInThisSession;
                        await this.sendDiscordWebhook(user, true, null, accountWasCreated);
                        
                        // Update CSV to mark entry as completed
                        this.log('💾 Updating CSV: marking entry as completed...');
                        const csvHelper = new CsvHelper();
                        await csvHelper.readCsvData();
                        const entryUpdated = await csvHelper.markEntryCompleted(user.EMAIL);
                        if (entryUpdated) {
                            this.log('CSV updated: ENTERED = TRUE');
                        } else {
                            this.log('⚠️ Failed to update CSV for entry completion');
                        }
                        
                        this.log('FIFA automation completed successfully!');
                        return true;
                    }else{
                        this.log('🎯 Draw entry needed after login...');
                        await this.handleDrawEntry();
                        return true;
                    }
                } else {
                    throw new Error('Login failed after user exists detection');
                } 
            } else {
                // Handle account registration
                const registered = await this.handleAccountRegistration(user);
                if(registered === 'USER_EXISTS_SWITCHED_TO_LOGIN'){
                    this.log('🔄 User already exists - switching to login flow');
                    // Continue with login flow since we're now on the login form
                    const loginFilled = await this.fillLoginFormRobust(user);
                    if (!loginFilled) {
                        throw new Error('Failed to fill login form after 60 seconds - proxy may be blocked');
                    }

                    // Ensure cookie banner is not blocking before login
                    await this.ensureCookieBannerNotBlocking();
                    
                    // Click login button (robust method)
                    const loginClicked = await this.humanInteractions.clickLoginButtonRobust();
                    if (!loginClicked) {
                        throw new Error('Failed to click login button after 60 seconds - proxy may be blocked');
                    }
                } 
    

                const loginResult = await this.handleLoginResult();
                    
                if (loginResult === 'EMAIL_VERIFICATION_NEEDED') {
                    this.markAccountAsCreated(user);
                    this.log('📧 Email verification needed, handling OTP verification...');
                    await this.handleEmailVerification(user);
                    
                    // After email verification, check what's needed next
                    const needsAccountCompletion = await this.checkIfAccountCompletionNeeded();
                    if (needsAccountCompletion) {
                        this.log('📝 Account completion needed after email verification (user exists case)...');
                        await this.handleAccountCompletion(user);
                        return true; // handleAccountCompletion already handles draw entry and webhook
                    }
                    
                    // Proceed to draw entry
                    const drawEntryResult = await this.handleDrawEntry();
                    if (drawEntryResult === 'RESTART_DRAW_ENTRY') {
                        this.log('🔄 Page reloaded during draw entry - restarting from draw entry');
                        await this.handleDrawEntry();
                    }
                    await this.handleCompletionAndWebhook(user);
                    return true;
                    
                } else if(loginResult === 'ACCOUNT_COMPLETION_NEEDED') {
                    this.log('📝 Account completion needed after login...');
                    await this.handleAccountCompletion(user);
                    return true; // handleAccountCompletion already handles draw entry and webhook
                }else if(loginResult === 'DRAW_ENTRY_NEEDED'){
                    // first check if draw maybe not already entered
                    await this.page.waitForLoadState('domcontentloaded', { timeout: 30000 });
                    const completionDetected = await this.detectCompletionPage();
                    if (completionDetected) {
                        this.log('🎉 Entry completion page detected!');
                        const accountWasCreated = user && user.accountCreatedInThisSession;
                        await this.sendDiscordWebhook(user, true, null, accountWasCreated);
                        
                        // Update CSV to mark entry as completed
                        this.log('💾 Updating CSV: marking entry as completed...');
                        const csvHelper = new CsvHelper();
                        await csvHelper.readCsvData();
                        const entryUpdated = await csvHelper.markEntryCompleted(user.EMAIL);
                        if (entryUpdated) {
                            this.log('CSV updated: ENTERED = TRUE');
                        } else {
                            this.log('⚠️ Failed to update CSV for entry completion');
                        }
                        
                        this.log('FIFA automation completed successfully!');
                        return true;
                    }else{
                        this.log('🎯 Draw entry needed after login...');
                        await this.handleDrawEntry();
                        return true;
                    }

                } else {
                    throw new Error('Login failed after user exists detection');
                }


                if (registered === 'USER_EXISTS_SWITCHED_TO_LOGIN') {
                   
                    
                    // Now handle login result properly (same as existing account login)
                    
                    
                } else if (!registered) {
                    throw new Error('Failed to register account - proxy may be blocked');
                }
                
                // Update CSV to mark account as created (only for NEW registrations, not existing users)
                
                
               
                return true;
            }

            // Wait for login result and handle redirects (for existing accounts only)
           
            
            // Note: For new registrations, account completion and draw entry are handled above

            this.log('FIFA automation main flow completed!');
            return true;

        } catch (error) {
            console.error('❌ FIFA automation failed:', error.message);
            
            // Handle CAPTCHA block specially  
            if (error.message === 'CAPTCHA_BLOCKED') {
                this.log('🤖 CAPTCHA block detected - proxy/IP is flagged, need to switch');
                const currentUserData = user || this.currentUser;
                
                // Send CAPTCHA blocked webhook
                await this.sendDiscordWebhook(currentUserData, false, 'CAPTCHA block detected - proxy flagged', false);
                
                // Don't mark user as blocked in CSV (it's a proxy issue, not account issue)
                // Let the main worker handle proxy/profile deletion and retry
                throw new Error('PROXY_TIMEOUT'); // Use PROXY_TIMEOUT to trigger retry logic
            }
            
            // Check if the user was actually completed despite the error
            let wasCompleted = false;
            try {
                const csvHelper = new CsvHelper();
                await csvHelper.readCsvData();
                const userData = csvHelper.data.find(u => u.EMAIL === (user?.EMAIL || this.currentUser?.EMAIL));
                if (userData && userData.ENTERED === 'TRUE') {
                    wasCompleted = true;
                    this.log('User was actually completed (CSV shows ENTERED=TRUE) despite error');
                }
            } catch (csvError) {
                this.log(`⚠️ Could not check CSV status: ${csvError.message}`);
            }
            
            // Send failure webhook - use currentUser if user is not defined
            const currentUserData = user || this.currentUser;
            const accountWasCreated = currentUserData && currentUserData.accountCreatedInThisSession;
            await this.sendDiscordWebhook(currentUserData, false, error.message, accountWasCreated);
            
            // If the user was actually completed, return true instead of throwing
            if (wasCompleted) {
                this.log('Returning true despite error since user was completed');
                return true;
            }
            
            throw error;
        } finally {
            this.isRunning = false;
        }
    }

    /**
     * Handle completion detection and webhook sending
     */
    async handleCompletionAndWebhook(user) {
        try {
            this.log('🔍 Checking for completion and sending webhook...');
            
            // Wait longer for completion page to appear (submission can take time)
            this.log('Waiting for submission to complete (up to 90 seconds)...');
            
            let completionDetected = false;
            const maxWaitSeconds = 90;
            let waitedSeconds = 0;
            
            // Check every 5 seconds for completion
            while (!completionDetected && waitedSeconds < maxWaitSeconds) {
                await this.page.waitForTimeout(5000); // Wait 5 seconds
                waitedSeconds += 5;
                
                if (waitedSeconds % 15 === 0) {
                    this.log(`🔄 Still waiting for completion... (${waitedSeconds}/${maxWaitSeconds} seconds)`);
                }
                
                completionDetected = await this.detectCompletionPage();
                
                if (completionDetected) {
                    this.log(`Completion detected after ${waitedSeconds} seconds!`);
                    break;
                }
            }
            
            if (completionDetected) {
                this.log('🎉 Entry completion page detected!');
                
                // Send Discord webhook notification
                const accountWasCreated = user && user.accountCreatedInThisSession;
                await this.sendDiscordWebhook(user, true, null, accountWasCreated);
                
                // Update CSV to mark entry as completed
                this.log('💾 Updating CSV: marking entry as completed...');
                const csvHelper = new CsvHelper();
                await csvHelper.readCsvData();
                const entryUpdated = await csvHelper.markEntryCompleted(user.EMAIL);
                if (entryUpdated) {
                    this.log('CSV updated: ENTERED = TRUE');
                } else {
                    this.log('⚠️ Failed to update CSV for entry completion');
                }
                
                this.log('FIFA automation completed successfully!');
                return true;
            } else {
                this.log(`⚠️ Completion page not detected after ${maxWaitSeconds} seconds - submission may have timed out`);
                
                // Send timeout webhook (not failure, but timeout warning)
                const accountWasCreated = user && user.accountCreatedInThisSession;
                const timeoutMessage = `Submission timed out after ${maxWaitSeconds} seconds. Entry might have been submitted successfully but confirmation page didn't load. Check manually.`;
                
                await this.sendDiscordWebhook(user, false, timeoutMessage, accountWasCreated);
                
                // Don't update CSV to ENTERED = TRUE since we're not sure
                this.log('⚠️ Not updating CSV to ENTERED = TRUE due to timeout uncertainty');
                
                this.log('⚠️ FIFA automation timed out - entry status uncertain');
                return false; // Return false to indicate uncertainty
            }
            
        } catch (error) {
            this.log(`⚠️ Error in completion handling: ${error.message}`);
            // Still try to send webhook and update CSV
            try {
                const accountWasCreated = user && user.accountCreatedInThisSession;
                await this.sendDiscordWebhook(user, true, null, accountWasCreated);
                const csvHelper = new CsvHelper();
                await csvHelper.readCsvData();
                await csvHelper.markEntryCompleted(user.EMAIL);
            } catch (fallbackError) {
                this.log(`⚠️ Fallback completion handling failed: ${fallbackError.message}`);
            }
        }
    }

    /**
     * Detect if we're on the completion page
     */
    async detectCompletionPage() {
        try {
            this.log('🔍 Checking for completion page indicators...');
            
            const completionIndicators = [
                ':text("Entry Completed")',                    // Main completion text
                ':text("Your entry for the FIFA World Cup")', // Success message
                ':text("Thank you for submitting")',          // Thank you message
                '.stx-lt-subscriptionSummary-note',           // Note container
                'button[aria-label="Cancel entry"]',          // Cancel entry button
                'button[aria-label="Edit choices"]',          // Edit choices button
                ':text("Pending")',                           // Status text
                '.stx-performance-subscribeState-OPEN'       // Status class
            ];
            
            let foundIndicators = 0;
            for (const selector of completionIndicators) {
                try {
                    const count = await this.page.locator(selector).count();
                    if (count > 0) {
                        foundIndicators++;
                        this.log(`Found completion indicator: ${selector}`);
                    }
                } catch (error) {
                    // Ignore individual selector errors
                }
            }
            
            this.log(`📊 Found ${foundIndicators} completion indicators`);
            return foundIndicators >= 3; // Need at least 3 indicators to be confident
            
        } catch (error) {
            this.log(`⚠️ Error detecting completion page: ${error.message}`);
            return false;
        }
    }

    /**
     * Send Discord webhook notification
     */
    async sendDiscordWebhook(user, isSuccess = true, errorMessage = null, accountCreated = false) {
        try {
            this.log('📡 Sending Discord webhook notification...');
            
            // Skip error webhooks for now (as requested)
            if (!isSuccess && errorMessage) {
                this.log('⚠️ Error webhook skipped (disabled)');
                return;
            }
            
            // Check if user is defined for success webhooks
            if (!user) {
                console.error('❌ Cannot send success webhook: user is undefined');
                return;
            }
            
            // Get webhook URL from settings
            const SettingsHelper = require('../helpers/settingsHelper');
            const settings = SettingsHelper.getInstance();
            const webhookUrl = settings.get('DISCORD_WEBHOOK');
            
            // DEBUG: Log the webhook URL being used
            this.log(`🔍 DEBUG: Using webhook URL: ${webhookUrl}`);
            
            // Get last 4 digits of credit card
            const last4 = user.CARD_NUM ? user.CARD_NUM.slice(-4) : 'N/A';
            
            // Get actual selected venues from class property or default
            let selectedVenues = this.selectedVenues || 'All venues except Monterrey (15/16 venues selected)';
            
            let embed;
            
            if (isSuccess) {
                embed = {
                    title: ':white_check_mark: FIFA World Cup Entry Completed!',
                    description: 'Successfully entered the FIFA World Cup 26™ Presale Draw for Visa® Cardholders',
                    color: 0x2E8DD6, // blue color for success #2E8DD6
                    fields: [
                        {
                            name: ':envelope: Email',
                            value: user.EMAIL || 'N/A',
                            inline: true
                        },
                        {
                            name: ':key: Password',
                            value: user.PASSWORD || 'N/A',
                            inline: true
                        },
                        {
                            name: ':credit_card: Card (Last 4)',
                            value: `****${last4}`,
                            inline: true
                        },
                          {
                             name: ':tada: Fan of',
                             value: this.currentUser?.FAN_OF,
                             inline: false
                          },
                        {
                            name: ':bust_in_silhouette: Account Info',
                            value: `${this.generatedAddress?.FIRST_NAME || user.FIRST_NAME || 'John'} ${this.generatedAddress?.LAST_NAME || user.LAST_NAME || 'Doe'}`,
                            inline: true
                        },
                        {
                            name: 'Phone',
                            value: this.generatedAddress?.PHONE_NUMBER || user.PHONE_NUMBER || '0612345678',
                            inline: true
                        }
                    ],
                    footer: {
                        text: 'FIFA World Cup 26™ Automation - SUCCESS'
                    },
                    timestamp: new Date().toISOString()
                };
                
            
            } else {
                // Failure webhook
                embed = {
                    title: ':x: FIFA World Cup Entry Failed!',
                    description: `Failed to complete FIFA World Cup 26™ Presale Draw entry`,
                    color: 0xff0000, // Red color for failure
                    fields: [
                        {
                            name: ':envelope: Email',
                            value: user.EMAIL || 'N/A',
                            inline: true
                        },
                        {
                            name: ':bust_in_silhouette: Account Info',
                            value: `${this.generatedAddress?.FIRST_NAME || user.FIRST_NAME || 'John'} ${this.generatedAddress?.LAST_NAME || user.LAST_NAME || 'Doe'}`,
                            inline: true
                        },
                        {
                            name: ':warning: Error Reason',
                            value: errorMessage || 'Unknown error',
                            inline: false
                        }
                    ],
                    footer: {
                        text: 'FIFA World Cup 26™ Automation - FAILED'
                    },
                    timestamp: new Date().toISOString()
                };
                
                // Add account creation notice if applicable
                if (accountCreated) {
                    embed.fields.splice(2, 0, {
                        name: ':new: Account Status',
                        value: 'New account was created, but entry failed after that',
                        inline: false
                    });
                }
            }
            
            const payload = {
                embeds: [embed]
            };
            
            const response = await fetch(webhookUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            if (response.ok) {
                this.log('Discord webhook sent successfully!');
            } else {
                this.log(`⚠️ Discord webhook failed with status: ${response.status}`);
            }
            
        } catch (error) {
            this.log(`⚠️ Error sending Discord webhook: ${error.message}`);
        }
    }

    /**
     * Wait for page to load using element detection instead of network state
     */
    async waitForPageLoadWithElements() {
        try {
            this.log('🔍 Waiting for page load using element detection...');
            
            // Wait for basic page structure to be present
            const pageLoadIndicators = [
                'body',                                    // Basic body element
                '#content',                               // Main content container
                '#main_content_container',                // Main content
                'section',                                // Any section element
                'form',                                   // Any form element
                '.content',                               // Content class
                'h1, h2, h3',                            // Any heading
                'button',                                 // Any button
                'input'                                   // Any input
            ];
            
            let pageLoaded = false;
            const maxWait = 30; // 30 seconds max
            let attempts = 0;
            
            while (!pageLoaded && attempts < maxWait) {
                attempts++;
                
                if (attempts % 5 === 0) {
                    this.log(`🔄 Checking page load... (${attempts}/${maxWait} seconds)`);
                }
                
                // Check if any of the indicators are present
                let foundElements = 0;
                for (const selector of pageLoadIndicators) {
                    try {
                        const count = await this.page.locator(selector).count();
                        if (count > 0) {
                            foundElements++;
                        }
                    } catch (error) {
                        // Ignore individual selector errors
                    }
                }
                
                // Consider page loaded if we found multiple elements
                if (foundElements >= 3) {
                    pageLoaded = true;
                    this.log(`Page loaded successfully (found ${foundElements} elements)`);
                    break;
                }
                
                // Wait 1 second before next check
                await this.page.waitForTimeout(1000);
            }
            
            if (!pageLoaded) {
                this.log('⚠️ Page load detection timed out after 30 seconds, but continuing anyway...');
            }
            
            // Additional small wait for any dynamic content
            await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
            
        } catch (error) {
            this.log(`⚠️ Error in page load detection: ${error.message}`);
            // Don't throw error, just continue
        }
    }

    /**
     * Check if account completion is needed (venues, address, etc.)
     */
    async checkIfAccountCompletionNeeded() {
        try {
            this.log('🔍 Checking if account completion is needed...');
            
            // Wait for page to stabilize after potential navigation
            await this.page.waitForLoadState('domcontentloaded', { timeout: 10000 });
            await this.page.waitForTimeout(2000); // Additional wait for any dynamic content
            
            const captchaElement = await pageContext.locator('.captcha__footer').isVisible({ timeout: 500 });
            if (captchaElement) {
                this.log(`🤖 CAPTCHA detected while waiting for ${elementName} - proxy/IP is blocked`);
                throw new Error('CAPTCHA_BLOCKED');
            }

            // Get page title
            let pageTitle = '';
            try {
                pageTitle = await this.page.title();
                this.log(`📄 Page title: ${pageTitle}`);
            } catch (titleError) {
                this.log(`⚠️ Could not get page title (page may be navigating): ${titleError.message}`);
                // Wait a bit more and try again
                await this.page.waitForTimeout(3000);
                try {
                    pageTitle = await this.page.title();
                    this.log(`📄 Page title (retry): ${pageTitle}`);
                } catch (retryError) {
                    this.log(`⚠️ Still could not get page title: ${retryError.message}`);
                    // If we can't get page title, assume completion is needed for safety
                    this.log('📝 Cannot determine page state - assuming account completion is needed');
                    return true;
                }
            }
            
            // Simple and reliable logic based on page title
            if (pageTitle.includes('Draw Entry - FIFA')) {
                this.log('On draw entry page - account completion is already done');
                return false;
            } else if (pageTitle.includes('Complete your account - FIFA')) {
                this.log('📝 On account completion page - account completion still needs to be done');
                return true;
            } else {
                // For any other page title, assume completion is needed for safety
                this.log(`📝 Unknown page title "${pageTitle}" - assuming account completion is needed`);
                return true;
            }
            
        } catch (error) {
            this.log(`⚠️ Error checking account completion status: ${error.message}`);
            return true; // Default to needed on error for safety
        }
    }

    /**
     * Wait for draw entry elements to appear on the page
     * @param {number} maxWaitSeconds - Maximum time to wait in seconds
     * @returns {boolean} True if draw entry elements found, false if timeout
     */
    async waitForDrawEntryElements(maxWaitSeconds = 20) {
        try {
            this.log(`🔍 Waiting for draw entry elements (up to ${maxWaitSeconds} seconds)...`);
            
            const drawEntrySelectors = [
                'button[aria-label="Enter Draw"]',
                'button:has-text("Enter Draw")',
                'button:has-text("Apply")',
                'button:has-text("Enter")',
                '.stx-p-button:has-text("Enter Draw")',
                '.p-button:has-text("Enter Draw")',
                'button:has-text("Submit Entry")',
                'button:has-text("Confirm Application")'
            ];
            
            const maxAttempts = maxWaitSeconds;
            let attempts = 0;
            
            while (attempts < maxAttempts) {
                attempts++;
                
                if (attempts % 5 === 0) {
                    this.log(`🔄 Still waiting for draw entry elements... (${attempts}/${maxWaitSeconds} seconds)`);
                }
                
                // Check each selector
                for (const selector of drawEntrySelectors) {
                    try {
                        const count = await this.page.locator(selector).count();
                        if (count > 0) {
                            this.log(`Found draw entry element: ${selector}`);
                            return true;
                        }
                    } catch (error) {
                        // Continue checking other selectors
                    }
                }
                
                // Also check if we're on the tickets page
                const currentUrl = this.page.url();
                if (currentUrl.includes('tickets.fifa.com') && !currentUrl.includes('account')) {
                    this.log('On tickets page, checking for any draw-related content...');
                    
                    // Check for any draw-related text or elements
                    try {
                        const pageContent = await this.page.content();
                        const drawIndicators = [
                            'enter draw',
                            'apply for',
                            'lottery',
                            'ticket',
                            'world cup'
                        ];
                        
                        const hasDrawContent = drawIndicators.some(indicator => 
                            pageContent.toLowerCase().includes(indicator.toLowerCase())
                        );
                        
                        if (hasDrawContent) {
                            this.log('Found draw-related content on tickets page');
                            return true;
                        }
                    } catch (contentError) {
                        // Continue waiting
                    }
                }
                
                // Wait 1 second before next check
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            this.log(`⚠️ No draw entry elements found after ${maxWaitSeconds} seconds`);
            return false;
            
        } catch (error) {
            this.log(`⚠️ Error waiting for draw entry elements: ${error.message}`);
            return false;
        }
    }

    /**
     * Check if email verification is needed based on URL and page content
     * @returns {boolean} True if email verification needed, false otherwise
     */
    async checkIfEmailVerificationNeeded() {
        try {
            const currentUrl = this.page.url();
            this.log(`🔍 Checking if email verification needed for URL: ${currentUrl}`);
            
            // Check URL patterns that indicate email verification is needed
            const emailVerificationPatterns = [
                'scope=openid+email',
                'auth.fifa.com/as/authorize',
                'response_type=code',
                'scope=openid',
                'verify',
                'verification',
                'otp',
                '2fa',
                'two-factor'
            ];
            
            const urlIndicatesEmailVerification = emailVerificationPatterns.some(pattern => 
                currentUrl.toLowerCase().includes(pattern.toLowerCase())
            );
            
            if (urlIndicatesEmailVerification) {
                this.log('Checking page');
                
                // Check for SPECIFIC email verification form elements (not login form)
                const emailVerificationSelectors = [
                    'input[name="otp"]',
                    'input[id="otp"]',
                    'input[placeholder="Enter Code"]',
                    'input[name="code"]',
                    'input[name="verificationCode"]',
                    'input[placeholder*="verification" i]',
                    'input[placeholder*="otp" i]',
                    'input[placeholder*="code" i]',
                    'input[id*="verification"]',
                    'input[id*="code"]',
                    'button[id="auto-submit"]',
                    'button:has-text("Verify My Code")',
                    '.verify-container',
                    '.verify-content-form-container',
                    '.verify-content-form',
                    'h1:has-text("Check your email")',
                    'h2:has-text("one click away from completing")',
                    '[class*="verification"]',
                    '[class*="otp"]',
                    'label:has-text("OTP")',
                    'label:has-text("Verification")',
                    'label:has-text("Code")',
                    'h1:has-text("Verify")',
                    'h2:has-text("Verify")',
                    'h1:has-text("Email Verification")',
                    'h2:has-text("Email Verification")'
                ];
                
                for (const selector of emailVerificationSelectors) {
                    try {
                        const count = await this.page.locator(selector).count();
                        if (count > 0) {
                            this.log(`Found email verification form element: ${selector}`);
                            return true;
                        }
                    } catch (error) {
                        // Continue checking other selectors
                    }
                }
                
                // Additional check: look for text content that indicates email verification
                try {
                    const pageText = await this.page.textContent('body');
                    if (pageText && (
                        pageText.includes('verification code') ||
                        pageText.includes('Verification Code') ||
                        pageText.includes('Enter the code') ||
                        pageText.includes('Enter Code') ||
                        pageText.includes('check your email') ||
                        pageText.includes('Check your email') ||
                        pageText.includes('one click away from completing') ||
                        pageText.includes('Verify My Code') ||
                        pageText.includes('Didn\'t receive the email') ||
                        pageText.includes('Check your spam folder') ||
                        pageText.includes('OTP') ||
                        pageText.includes('One-Time Password')
                    )) {
                        this.log(`Found email verification text content: "Check your email" or "Enter Code"`);
                        return true;
                    }
                } catch (error) {
                    // Continue
                }
                
                // If URL indicates email verification but no specific form found, it's probably just login page
                this.log('⚠️ Still on login page');
                return false;
            }
            
            // Also check page content for verification indicators
            try {
                const pageContent = await this.page.content();
                const contentIndicators = [
                    'verify your email',
                    'email verification',
                    'enter the code',
                    'verification code',
                    'check your email',
                    'otp code',
                    'two-factor'
                ];
                
                const contentIndicatesVerification = contentIndicators.some(indicator => 
                    pageContent.toLowerCase().includes(indicator.toLowerCase())
                );
                
                if (contentIndicatesVerification) {
                    this.log('📧 Page content indicates email verification is needed');
                    return true;
                }
            } catch (contentError) {
                this.log(`⚠️ Could not check page content: ${contentError.message}`);
            }
            
            this.log('No email verification needed');
            return false;
            
        } catch (error) {
            console.error('❌ Error checking email verification status:', error.message);
            return false;
        }
    }

    /**
     * Check if user is already logged in by detecting account info or draw entry elements
     */
    async checkIfAlreadyLoggedIn() {
        try {
            this.log('🔍 Checking if user is already logged in...');
            
            // First check if we're on an email verification page - if so, not logged in yet
            const currentUrl = this.page.url();
            if (currentUrl.includes('scope=openid+email') || currentUrl.includes('auth.fifa.com/as/authorize')) {
                this.log('📧 On email verification page - not logged in yet');
                return false;
            }
            
            // Wait a moment for page to load
            await this.page.waitForTimeout(2000);
            
            // Check for indicators that user is already logged in
            const loginIndicators = [
                // Account info in sidebar
                '.account_info .account',                           // Account name link
                '.account_info .email',                            // Email display
                'section.state-user-logged',                       // Logged in state class
                
                // Draw entry elements (main content)
                'button[aria-label="Enter Draw"]',                 // Enter Draw button
                'button.yes-btn',                                  // Yes button for new flow
                '#main_content_lottery_applications',              // Lottery applications section
                '.stx-container[loggerurl*="gravity"]',            // STX lottery widget
                
                // Page structure for logged-in users
                'h2:has-text("Draw Entry")',                       // Draw Entry title
                '.menu_pre_sales_waiting_list.selected',          // Selected menu item
                
                // Client account section
                '#secondary_content_navigation .menu_title:has-text("Client account")',
                
                // Registration completion and account setup indicators
                'form[action*="/account/register"]',               // Registration form (completion page)
                '.register_form',                                  // Registration form container
                'input[name="firstName"]',                         // First name field (account completion)
                'input[name="lastName"]',                          // Last name field (account completion)
                'select[name="fanOfCountry"]',                     // Fan country selector
                'select[name="venue"]',                            // Venue selector
                '.form-container',                                 // Form container on account pages
                
                // Navigation elements for logged-in users
                '.navigation .account',                            // Account navigation
                '.user-menu',                                      // User menu
                '.profile-menu'                                    // Profile menu
            ];
            
            let foundIndicators = 0;
            const foundSelectors = [];
            
            for (const selector of loginIndicators) {
                try {
                    const count = await this.page.locator(selector).count();
                    if (count > 0) {
                        foundIndicators++;
                        foundSelectors.push(selector);
                        this.log(`Found login indicator: ${selector}`);
                    }
                } catch (error) {
                    // Ignore individual selector errors
                }
            }
            
            // Also check URL patterns for logged-in users
            const pageUrl = this.page.url();
            const isLotteryUrl = pageUrl.includes('/account/lotteryApplications');
            const isRegisterUrl = pageUrl.includes('/account/register');
            const isAccountUrl = pageUrl.includes('/account/') && !pageUrl.includes('/auth');
            const isFifaTicketsUrl = pageUrl.includes('fifa-fwc26-us.tickets.fifa.com');
            
            this.log(`📍 Current URL: ${pageUrl}`);
            this.log(`🎯 Is lottery URL: ${isLotteryUrl}`);
            this.log(`🎯 Is register URL: ${isRegisterUrl}`);
            this.log(`🎯 Is account URL: ${isAccountUrl}`);
            this.log(`🎯 Is FIFA tickets domain: ${isFifaTicketsUrl}`);
            this.log(`Found ${foundIndicators} login indicators: ${foundSelectors.join(', ')}`);
            
            // Consider user logged in if:
            // 1. Found multiple indicators, OR
            // 2. On lottery page with at least 1 indicator, OR
            // 3. On FIFA tickets domain with account-related URL (register, account pages)
            const isLoggedIn = (foundIndicators >= 2) || 
                              (isLotteryUrl && foundIndicators >= 1) ||
                              (isFifaTicketsUrl && (isRegisterUrl || isAccountUrl));
            
            if (isLoggedIn) {
                this.log('User appears to be already logged in');
                
                // Try to get user info from page
                try {
                    const accountName = await this.page.locator('.account_info .account').first().textContent();
                    const accountEmail = await this.page.locator('.account_info .email').first().textContent();
                    this.log(`👤 Logged in as: ${accountName} (${accountEmail})`);
                } catch (error) {
                    this.log('ℹ️ Could not extract user info from page');
                }
            } else {
                this.log('❌ User does not appear to be logged in');
            }
            
            return isLoggedIn;
            
        } catch (error) {
            this.log(`⚠️ Error checking login status: ${error.message}`);
            return false; // Default to not logged in on error
        }
    }

    // Error webhook function removed as requested

    /**
     * Accept terms and submit (for saved cards)
     */
    async acceptTermsAndSubmit(maxRetries = 2) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`Attempt ${attempt}/${maxRetries} - Accepting terms and submitting with saved card...`);
            
            // Look for terms checkbox
            const checkboxSelectors = [
                'input[type="checkbox"]',
                '.p-checkbox-box',
                '[role="checkbox"]',
                'input[name*="terms"]',
                'input[name*="accept"]'
            ];
            
            let checkboxClicked = false;
            for (const selector of checkboxSelectors) {
                checkboxClicked = await this.humanInteractions.robustClick(selector, `Terms checkbox (${selector})`, null, 2, 60, this.log);
                if (checkboxClicked) {
                    this.log('Terms checkbox clicked');
                    break;
                }
            }
            
            if (!checkboxClicked) {
                this.log('⚠️ Terms checkbox not found or already checked');
            }
            
            // Wait a moment
            await this.page.waitForTimeout(UtilityHelper.randomDelay(1000, 2000));
            
            // Look for submit button
            const submitSelectors = [
                'button[aria-label="Submit Entry"]',
                'button:has-text("Submit Entry")',
                'button:has-text("Confirm Application")',
                'button:has-text("Submit")',
                'button[type="submit"]',
                '.p-button:has-text("Submit")'
            ];
            
            let submitClicked = false;
            for (const selector of submitSelectors) {
                submitClicked = await this.humanInteractions.robustClick(selector, `Submit button (${selector})`, null, 2, 60, this.log);
                if (submitClicked) {
                    this.log('Submit button clicked with saved card');
                    break;
                }
            }
            
                if (!submitClicked) {
                    throw new Error('Submit button not found');
                }
                
                this.log(`Terms accepted and submitted successfully on attempt ${attempt}!`);
                return; // Success, exit the retry loop
                
            } catch (error) {
                console.error(`❌ Error in acceptTermsAndSubmit on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to accept terms and submit after ${maxRetries} attempts`);
                    throw error;
                }
                
                // Wait before retry
                this.log(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
    }

    /**
     * Handle account completion form (venues, stages, personal details)
     */
    async handleAccountCompletion(user) {
        try {
            this.log('📝 Handling account completion form...');
            
            // Wait for account completion page to load
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
            
            // Check current URL to understand what page we're on
            const currentUrl = this.page.url();
            this.log(`📍 Current URL for account completion: ${currentUrl}`);
            
            // Check if we're on the personal details page
            const isPersonalDetailsPage = currentUrl.includes('editPersonalDetails') || 
                                        await this.page.locator('select[name="contactCriteria[VENUE].values"]').count() > 0;
            
            if (isPersonalDetailsPage) {
                this.log('📝 On personal details page, filling form in correct order...');
                
                // Step 1: Confirm 18+ age checkbox
                this.log('🔞 Step 1: Confirming 18+ age...');
                const ageConfirmed = await this.checkAgeConfirmation();
                if (ageConfirmed) {
                    this.log('Age confirmation completed');
                } else {
                    this.log('⚠️ Age confirmation not found or failed, continuing...');
                }
                
                // Step 2: Fill interest in rounds/stages
                this.log('🏆 Step 2: Selecting interest in rounds...');
                const roundsSelected = await this.selectRoundsInterest();
                if (roundsSelected) {
                    this.log('Rounds interest completed');
                } else {
                    this.log('⚠️ Rounds interest not found or failed, continuing...');
                }
                
                // Step 2.5: Select "Fan of" country
                this.log('🏴 Step 2.5: Selecting fan of country...');
                const fanOfSelected = await this.selectFanOfCountry();
                if (fanOfSelected) {
                    this.log('Fan of country completed');
                } else {
                    this.log('⚠️ Fan of country not found or failed, continuing...');
                }
                
                // Step 2.6: Accept Stadium Code of Conduct
                this.log('📜 Step 2.6: Accepting Stadium Code of Conduct...');
                const conductAccepted = await this.acceptStadiumCodeOfConduct();
                if (conductAccepted) {
                    this.log('Stadium Code of Conduct accepted');
                } else {
                    this.log('⚠️ Stadium Code of Conduct not found or failed, continuing...');
                }
                
                // Step 3: Select multiple venues
                this.log('🏟️ Step 3: Selecting venues...');
                const venueSelected = await this.selectMultipleVenues();
                if (venueSelected) {
                    this.log('Venue selection completed');
                } else {
                    this.log('⚠️ Venue selection failed, continuing anyway...');
                }
                
                // Step 4: Fill address information
                this.log('🏠 Step 4: Filling address information...');
                await this.fillAddressForm(user);
                
                // Look for and click Save/Submit button (correct priority based on HTML)
                const saveSelectors = [
                    'a[id="save"]',                          // PRIMARY from HTML
                    'span[id="saveButton"] a',               // Alternative from HTML  
                    '#saveButton a',                         // Alternative
                    'button:has-text("Save")',               // Fallback
                    'button[type="submit"]',                 // Fallback
                    'input[type="submit"]'                   // Fallback
                ];
                
                let saveClicked = false;
                for (const selector of saveSelectors) {
                    saveClicked = await this.humanInteractions.robustClick(selector, `Save button (${selector})`, null, 2, 60, this.log);
                    if (saveClicked) {
                        break;
                    }
                }
                
                if (saveClicked) {
                    this.log('Account completion form saved');
                    await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 3000));
                } else {
                    this.log('⚠️ Save button not found, may already be saved');
                }
            }
            
            // Check if we're redirected to lottery applications page after form submission
            const finalUrl = this.page.url();
            this.log(`📍 Current URL after account completion: ${finalUrl}`);
            
            if (finalUrl.includes('lotteryApplications')) {
                this.log('Redirected to lottery applications page - continuing with draw entry...');
                const drawEntryResult = await this.handleDrawEntry();
                if (drawEntryResult === 'RESTART_DRAW_ENTRY') {
                    this.log('🔄 Page reloaded during draw entry - restarting from draw entry');
                    await this.handleDrawEntry();
                }
                
                // After draw entry is complete, check for completion and send webhook
                await this.handleCompletionAndWebhook(user);
            } else {
                this.log('⚠️ Not on lottery applications page, may need manual intervention');
            }
            
        } catch (error) {
            console.error('❌ Error in account completion:', error.message);
            throw error;
        }
    }

    /**
     * Select interest in rounds/stages (ROT checkboxes)
     */
    async selectRoundsInterest() {
        try {
            this.log('🏆 Selecting interest in tournament rounds...');
            
            // Based on the actual HTML, ROT are checkboxes with name="contactCriteria[ROT].values"
            const rotCheckboxes = await this.page.locator('input[name="contactCriteria[ROT].values"]').all();
            
            this.log(`🎯 Found ${rotCheckboxes.length} Round of Tournament checkboxes`);
            
            if (rotCheckboxes.length === 0) {
                this.log('⚠️ No ROT checkboxes found');
                return false;
            }
            
            let roundsSelected = 0;
            
            // Select all round checkboxes (or most of them)
            for (let i = 0; i < rotCheckboxes.length; i++) {
                try {
                    const checkbox = rotCheckboxes[i];
                    
                    // Get the value and label text
                    const value = await checkbox.getAttribute('value');
                    const id = await checkbox.getAttribute('id');
                    
                    // Get the label text
                    let labelText = 'Unknown';
                    try {
                        const label = this.page.locator(`label[for="${id}"]`);
                        labelText = await label.textContent();
                    } catch (error) {
                        // Ignore label errors
                    }
                    
                    this.log(`📍 Round ${i+1}: ${value} - ${labelText}`);
                    
                    // Check if already selected
                    const isChecked = await checkbox.isChecked();
                    if (!isChecked) {
                        await checkbox.click();
                        roundsSelected++;
                        this.log(`Selected round: ${labelText} (${value})`);
                        
                        // Small delay between selections
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
                    } else {
                        this.log(`ℹ️ Round already selected: ${labelText}`);
                    }
                    
                } catch (error) {
                    this.log(`⚠️ Failed to select round ${i+1}: ${error.message}`);
                }
            }
            
            this.log(`Selected ${roundsSelected} rounds out of ${rotCheckboxes.length} available`);
            return roundsSelected > 0;
            
        } catch (error) {
            this.log(`⚠️ Error selecting rounds interest: ${error.message}`);
            return false;
        }
    }

    /**
     * Select "Fan of" country
     */
    async selectFanOfCountry() {
        try {
            this.log('🏴 Selecting fan of country...');
            
            // Get FAN_OF value from user data
            const fanOfCountry = this.currentUser?.FAN_OF;
            if (!fanOfCountry) {
                this.log('⚠️ FAN_OF not found in user data, using NED as default');
            }
            
            const countryCode = fanOfCountry || 'NED'; // Default to Netherlands if not specified
            this.log(`📍 Using country code: ${countryCode}`);
            
            // Based on HTML: select[name="contactCriteria[FanOF26].values[0]"]
            const fanOfSelector = 'select[name="contactCriteria[FanOF26].values[0]"]';
            const found = await this.humanInteractions.waitForElementRobust(fanOfSelector, 'Fan of country dropdown', null, 60, this.log);
            if (!found) {
                this.log('⚠️ Fan of country dropdown not found');
                return false;
            }
            
            // Select the country from CSV data
            const selected = await this.humanInteractions.robustSelect(fanOfSelector, countryCode, `Fan of Country (${countryCode})`, null, 2, 60, this.log);
            if (selected) {
                this.log(`Successfully selected fan of country: ${countryCode}`);
            } else {
                this.log(`❌ Failed to select fan of country: ${countryCode}`);
            }
            
            return selected;
            
        } catch (error) {
            this.log(`⚠️ Error selecting fan of country: ${error.message}`);
            return false;
        }
    }

    /**
     * Accept Stadium Code of Conduct (skip if not found)
     */
    async acceptStadiumCodeOfConduct() {
        try {
            this.log('📜 Checking for Stadium Code of Conduct...');
            
            // Based on HTML: input[name="contactCriteria[STXCOC].values"] with value="YES"
            const count = await this.page.locator('input[name="contactCriteria[STXCOC].values"][value="YES"]').count();
            
            if (count === 0) {
                this.log('ℹ️ Stadium Code of Conduct not present on this form, skipping...');
                return true; // Return true to continue the flow
            }
            
            this.log('Found Stadium Code of Conduct checkbox');
            const conductCheckbox = this.page.locator('input[name="contactCriteria[STXCOC].values"][value="YES"]').first();
            
            // Check if already selected
            const isChecked = await conductCheckbox.isChecked();
            if (!isChecked) {
                // Try to click with a shorter timeout
                try {
                    await conductCheckbox.click({ timeout: 5000 });
                    this.log('Accepted Stadium Code of Conduct');
                } catch (clickError) {
                    this.log('⚠️ Could not click Stadium Code of Conduct, but continuing...');
                }
                
                // Small delay
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
            } else {
                this.log('ℹ️ Stadium Code of Conduct already accepted');
            }
            
            return true;
            
        } catch (error) {
            this.log(`ℹ️ Stadium Code of Conduct not available, continuing: ${error.message}`);
            return true; // Don't fail the process
        }
    }

    /**
     * Fill address form on personal details page
     */
    async fillAddressForm(user) {
        try {
            this.log('🏠 Filling address information...');
            
            // Address field mappings based on actual HTML
            const addressFields = [
                {
                    selectors: [
                        'input[name="addressLine1"]',        // Primary from HTML
                        'input[id="address_line_1"]'         // Alternative from HTML
                    ],
                    value: this.generatedAddress?.STREET_AND_NUMBER || user.STREET_AND_NUMBER || '123 Main Street',
                    name: 'Address Line 1'
                },
                {
                    selectors: [
                        'input[name="zipCode"]',             // Primary from HTML  
                        'input[id="address_zipcode"]'        // Alternative from HTML
                    ],
                    value: this.generatedAddress?.POSTALCODE || user.POSTALCODE || '1000 AA',
                    name: 'Postal Code'
                },
                {
                    selectors: [
                        'input[name="city"]',                // Primary from HTML
                        'input[id="address_town"]'           // Alternative from HTML
                    ],
                    value: this.generatedAddress?.CITY || user.CITY || 'Amsterdam',
                    name: 'City'
                },
                {
                    selectors: [
                        'select[name="country"]',            // Primary from HTML
                        'select[id="address_country"]'       // Alternative from HTML
                    ],
                    value: this.getCountryCodeForAddress(this.currentUser?.ADDRESS_COUNTRY), // Map address country to form country
                    name: 'Country',
                    isSelect: true
                },
                {
                    selectors: [
                        'select[name="phonePrefix"]',        // Phone prefix from HTML
                        'select[id="phone_prefix"]'          // Alternative from HTML
                    ],
                    value: '31', // Netherlands +31
                    name: 'Phone Prefix',
                    isSelect: true
                },
                {
                    selectors: [
                        'input[name="phone"]',               // Phone number from HTML
                        'input[id="phone_number"]'           // Alternative from HTML
                    ],
                    value: this.cleanPhoneNumberForForm(this.generatedAddress?.PHONE_NUMBER || user.PHONE_NUMBER || '0612345678'),
                    name: 'Phone Number'
                }
            ];
            
            // Fill each address field
            for (const field of addressFields) {
                let fieldFilled = false;
                
                for (const selector of field.selectors) {
                    try {
                        if (field.isSelect) {
                            // Handle select dropdown
                            fieldFilled = await this.humanInteractions.robustSelect(selector, field.value, field.name, null, 2, 60, this.log);
                        } else {
                            // Handle input field
                            fieldFilled = await this.humanInteractions.robustFill(selector, field.value, field.name, null, 2, 60, this.log);
                        }
                        
                        if (fieldFilled) {
                            this.log(`${field.name} filled successfully`);
                            break;
                        }
                    } catch (error) {
                        this.log(`⚠️ Failed to fill ${field.name} with ${selector}: ${error.message}`);
                    }
                }
                
                if (!fieldFilled) {
                    this.log(`⚠️ Could not fill ${field.name} with any selector, continuing...`);
                }
                
                // Small delay between fields
                await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 600));
            }
            
            this.log('Address form filling completed');
            
        } catch (error) {
            this.log(`⚠️ Error filling address form: ${error.message}`);
            // Don't throw error, continue with the process
        }
    }

    /**
     * Select multiple venues using CTRL+click (for venue selection)
     */
    async selectMultipleVenues() {
        try {
            this.log('🏟️ Selecting multiple venues...');
            
            // Wait for venue dropdown to be available
            const venueSelector = 'select[name="contactCriteria[VENUE].values"]';
            const found = await this.humanInteractions.waitForElementRobust(venueSelector, 'Venue dropdown', null, 60, this.log);
            if (!found) {
                this.log('⚠️ Venue dropdown not found, skipping venue selection');
                return true; // Don't fail the entire process
            }
            
            const venueDropdown = this.page.locator(venueSelector).first();
            
            // Get all available venues first
            const allVenues = await venueDropdown.evaluate(select => {
                const venues = [];
                for (let option of select.options) {
                    if (option.value && option.value !== '') {
                        venues.push({
                            value: option.value,
                            text: option.text
                        });
                    }
                }
                return venues;
            });
            
            this.log(`🎯 Found ${allVenues.length} venues available:`);
            allVenues.forEach((venue, index) => this.log(`   ${index}: ${venue.value} - ${venue.text}`));
            
            // Select ALL venues except the last one
            const venuesToSelect = allVenues.slice(0, -1); // All except last
            const skippedVenue = allVenues[allVenues.length - 1];
            this.log(`🎯 Will select ${venuesToSelect.length} venues (ALL except ${skippedVenue.text}):`);
            venuesToSelect.forEach((venue, index) => this.log(`    ${index + 1}. ${venue.text}`));
            this.log(`   ✗ Skipping: ${skippedVenue.text}`);
            
            // First, click the dropdown to focus it
            await venueDropdown.click();
            await this.page.waitForTimeout(UtilityHelper.randomDelay(300, 500));
            
            // Use keyboard approach for proper CTRL+click simulation
            const modifierKey = process.platform === 'darwin' ? 'Meta' : 'Control';
            
            this.log(`🎯 Will select ${venuesToSelect.length} venues using ${modifierKey}+click`);
            
            // Method 1: Try using keyboard down/up with clicks
            try {
                this.log(`⌨️ Method 1: Holding down ${modifierKey} key and clicking options...`);
                
                // Hold down the modifier key
                await this.page.keyboard.down(modifierKey);
                
                // Select multiple options while holding CTRL/CMD
                for (let i = 0; i < venuesToSelect.length; i++) {
                    const venue = venuesToSelect[i];
                    
                    try {
                        this.log(`📍 Selecting venue ${i+1}/${venuesToSelect.length}: ${venue.text} (${venue.value})`);
                        
                        // Find the specific option
                        const optionSelector = `${venueSelector} option[value="${venue.value}"]`;
                        const option = this.page.locator(optionSelector);
                        
                        // Wait for option to be available
                        await option.waitFor({ state: 'attached', timeout: 5000 });
                        
                        // Click while CTRL/CMD is held down
                        await option.click();
                        
                        this.log(`Clicked venue: ${venue.text}`);
                        
                        // Longer delay between selections for more realistic behavior
                        await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
                        
                    } catch (error) {
                        this.log(`⚠️ Failed to select venue ${venue.text}: ${error.message}`);
                    }
                }
                
                // Release the modifier key
                await this.page.keyboard.up(modifierKey);
                this.log(`⌨️ Released ${modifierKey} key`);
                
            } catch (error) {
                this.log(`⚠️ Method 1 failed: ${error.message}`);
                
                // Make sure to release the key even if there was an error
                try {
                    await this.page.keyboard.up(modifierKey);
                } catch (releaseError) {
                    // Ignore release errors
                }
                
                // Method 2: Use programmatic selection as fallback
                this.log(`🔄 Method 2: Using programmatic selection...`);
                
                const valuesToSelect = venuesToSelect.map(v => v.value);
                await venueDropdown.evaluate((select, values) => {
                    // Clear all selections first
                    for (let option of select.options) {
                        option.selected = false;
                    }
                    
                    // Select the desired options
                    for (let option of select.options) {
                        if (values.includes(option.value)) {
                            option.selected = true;
                            this.log(`Programmatically selected: ${option.text}`);
                        }
                    }
                    
                    // Trigger change event
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                }, valuesToSelect);
                
                this.log(`🔄 Programmatically selected ${valuesToSelect.length} venues`);
            }
            
            // Small delay after all selections
            await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
            
            // Trigger change event to ensure form validation
            await venueDropdown.dispatchEvent('change');
            await venueDropdown.dispatchEvent('blur');
            
            // Verify selections
            const selectedValues = await venueDropdown.evaluate(select => {
                const selected = [];
                for (let option of select.options) {
                    if (option.selected) {
                        selected.push({
                            value: option.value,
                            text: option.text
                        });
                    }
                }
                return selected;
            });
            
            this.log(`Final venue selections (${selectedValues.length} selected):`);
            selectedValues.forEach(venue => this.log(`    ${venue.value}: ${venue.text}`));
            
            // Store selected venues for webhook
            this.selectedVenues = selectedValues.map(venue => venue.text).join(', ');
            
            if (selectedValues.length === 0) {
                this.log('⚠️ No venues were selected, trying alternative approach...');
                
                // Alternative approach: Use programmatic selection
                const valuesToSelect = venuesToSelect.map(v => v.value);
                await venueDropdown.evaluate((select, values) => {
                    for (let option of select.options) {
                        option.selected = values.includes(option.value);
                    }
                    // Trigger change event
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }, valuesToSelect);
                
                this.log(`🔄 Used programmatic selection for ${valuesToSelect.length} venues`);
            }
            
            // Small delay after completion
            await this.page.waitForTimeout(UtilityHelper.randomDelay(500, 1000));
            
            return true;
            
        } catch (error) {
            console.error('❌ Error selecting venues:', error.message);
            return false;
        }
    }

    /**
     * Close browser and cleanup
     */
    async close() {
        try {
            if (this.page) {
                await this.page.close();
            }
            if (this.context) {
                await this.context.close();
            }
            if (this.browser) {
                await this.browser.close();
            }
            this.log('🔒 Browser closed successfully');
        } catch (error) {
            console.error('❌ Error closing browser:', error.message);
        }
    }

    /**
     * Stop the automation
     */
    stop() {
        this.isRunning = false;
        this.log('🛑 FIFA automation stopped');
    }

    /**
     * Get automation status
     */
    getStatus() {
        return {
            isRunning: this.isRunning,
            timestamp: new Date().toISOString()
        };
    }
}

module.exports = FifaAutomation;