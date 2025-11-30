
import { chromium, firefox, webkit, Browser, BrowserContext, Page } from 'playwright';
import CsvHelper from '../helpers/csvHelper';
import { generateAddress } from '../helpers/addressHelper';
import DolphinAntyHelper from '../helpers/dolphinAntyHelper';
import HumanInteractions from '../helpers/humanInteractions';
import config from '../helpers/config';
import ProxyHelper from '../helpers/proxyHelper';
import UtilityHelper from '../helpers/utilityHelper';
import ProfileHelper from '../helpers/profileHelper';
import SettingsHelper from '../helpers/settingsHelper';

// helpers
import registerFill from './helpers/registerFill';
import addressFill from './helpers/AddressFill';
import queueHandler from './helpers/queueHandler';
import addCard from './helpers/ccFill';

import {sendDiscordWebhook, sendErrorNotification, sendAccountCreationNotification, sendDrawEntryNotification, sendQueuePassExpiredWebhook} from '../helpers/discordWebhook'


/* Error codes 
PROXY_TIMEOUT - rotate proxy
*/
// Types and interfaces
interface BrowserFingerprint {
    screenWidth: number;
    screenHeight: number;
    userAgent: {
        value: string;
    };
}

interface ProfileResult {
    profileData: BrowserFingerprint;
}

interface UserData {
    EMAIL: string;
    PASSWORD: string;
    HAS_ACCOUNT: boolean;
    ADDRESS_COUNTRY: string;
    accountCreatedInThisSession?: boolean;
    [key: string]: any;
}

interface GeneratedAddress {
    FIRST_NAME: string;
    [key: string]: any;
}

interface AutomationStatus {
    isRunning: boolean;
    timestamp: string;
}


class FifaAutomation {
    private browser: Browser | null = null;
    private context: BrowserContext | null = null;
    private page: Page | null = null;
    private imapHelper: any = null;
    private isRunning: boolean = false;
    private csvHelper: CsvHelper;
    private currentUser: UserData | null = null;
    public taskNumber: number | null = null;
    private generatedAddress: GeneratedAddress | null = null; // Store generated address data
    private retryCount: number = 0;
    private maxRetries: number = 3;
    private cookieBannerAccepted: boolean = false;
    
    // Profile management
    private profileHelper: ProfileHelper;
    
    // Proxy management
    private proxies: string[] | null = null;
    private assignedProxy: any = null;
    
    // Human interactions
    private humanInteractions: HumanInteractions | null = null;
    private profileFingerprint: BrowserFingerprint | null = null;

    constructor() {
        this.csvHelper = CsvHelper.getInstance();
        this.profileHelper = new ProfileHelper();
    }

    log(message: string, level: string = 'log'): void {
        UtilityHelper.log(message, level, this.taskNumber);
    }
   

    changePage(page: Page): void {
        this.page = page;
        if (this.humanInteractions) {
            this.humanInteractions.setPage(this.page);
        }
    }

    async testEntryFlow(imapHelper: any): Promise<void> {
        try {
            this.log('=== TEST ENTRY FLOW ===');
            this.imapHelper = imapHelper;
            // 1. Set hardcoded profile ID
            const TEST_PROFILE_ID = '683078432'; // TODO: Change this to your actual profile ID
            
            // 2. Start the existing profile
            this.log(`Starting existing profile: ${TEST_PROFILE_ID}`);
            const result = await this.profileHelper.startExistingProfile(TEST_PROFILE_ID, this.log.bind(this));
            
            if (!result.success) {
                throw new Error('Failed to start existing profile');
            }
            
            this.log('Profile started successfully');
            
            // Set profile fingerprint if available
            if (result.profileData) {
                this.profileFingerprint = result.profileData;
            }
            
            // 3. Initialize browser (reuse existing pages from Dolphin profile)
            this.log('Initializing browser...');
            await this.browserInit(true); // Reuse existing pages from Dolphin
            this.log('Browser initialized');
            
            // 4. Generate address for USA fan country
            this.log('Generating address for USA...');

            this.currentUser ={
                EMAIL: 'susaonne93ilierly@outlook.com',
                PASSWORD: 'vcEM9!$gJlRAVb',
                HAS_ACCOUNT: true,
                ENTERED: false,
                VERIFIED:true,
                OTP_ISSUE: false,
                ADDRESS_COUNTRY: 'USA',
                FAN_OF: 'USA',
                CARD_NUM: '5395710930111139',
                CARD_CVV: '050',
                EXPIRY_MONTH: '10',
                EXPIRY_YEAR: '2030'

            }
            
            
            this.generatedAddress = await UtilityHelper.generateAddressData(this.currentUser, 3, this.log.bind(this), 'entry');
            this.log(`Generated address: ${JSON.stringify(this.generatedAddress)}`);
            
            // 5. Initialize HumanInteractions
            if (!this.humanInteractions) {
                this.humanInteractions = new HumanInteractions(this.page as any);
            }

            

            // wait for page to load
            await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });


            //await this.fifa_login();
            
            const entryFlowResult = await this.fifa_completion('entry');
            this.log(`Entry flow result: ${entryFlowResult}`);
            if(entryFlowResult === 'ENTERED_DRAW'){
                this.log('Entry flow completed successfully', 'success');
                await sendDrawEntryNotification(this.currentUser as UserData, this.log.bind(this));
            }else{
                this.log('Entry flow failed', 'error');
            }
            
            this.log('=== TEST COMPLETE ===');
            
        } catch (error: any) {
            this.log(`Test failed: ${error.message}`, 'error');
            console.error(error);
        } finally {
            // Clean up - don't delete the profile in test mode
            this.log('Cleaning up...');
            if (this.browser) {
                await this.browser.close();
            }
        }
    }
     /**
     * Close browser and cleanup
     */
     async close(): Promise<void> {
        try {
            // FIRST: Stop the Dolphin profile (this stops the browser process)
            try {
                await this.profileHelper.stopProfile(this.log.bind(this));
            } catch (stopError: any) {
                console.error('Error stopping profile during close:', stopError.message);
            }
            
            // SECOND: Close Playwright connections
            if (this.page) {
                await this.page.close();
            }
            if (this.context) {
                await this.context.close();
            }
            if (this.browser) {
                await this.browser.close();
            }
            
            // THIRD: Delete the profile (skip stop since we already stopped it)
            try {
                await this.profileHelper.deleteProfile(this.log.bind(this), true);
            } catch (profileError: any) {
                console.error('Error deleting profile during close:', profileError.message);
            }
            
            this.log('Browser closed successfully');
        } catch (error: any) {
            console.error(' Error closing browser:', error.message);
            
             // Even if browser close fails, still try to stop and delete profile
            try {
                await this.profileHelper.stopProfile(this.log.bind(this));
                await this.profileHelper.deleteProfile(this.log.bind(this), true);
            } catch (cleanupError: any) {
                console.error('Error during cleanup:', cleanupError.message);
            }
        }
    }

    /**
     * Simulate human reading page after load (reduces detection)
     */
    private async simulatePageReading(): Promise<void> {
        if (!this.page || !this.humanInteractions) return;
        
        try {
            // Wait and "read" the page
            await this.page.waitForTimeout(this.humanInteractions.randomDelay(2000, 4000));
            await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(1500, 3000));
            
            // Random small scroll (humans scan pages)
            if (Math.random() < 0.6) { // 60% chance
                const scrollAmount = Math.floor(Math.random() * 300) + 100;
                await this.page.evaluate((amount) => {
                    window.scrollBy(0, amount);
                }, scrollAmount);
                await this.page.waitForTimeout(this.humanInteractions.randomDelay(500, 1000));
            }
        } catch (error: any) {
            // Silently continue if reading simulation fails
        }
    }

    async browserInit(reuseExistingPages: boolean = false): Promise<boolean> {
        try {
            
            const browserPath: any = this.profileHelper.getBrowserPath();
            if (!browserPath) {
                throw new Error('Browser path not available. Call createAndStartProfile() first.');
            }
            
            // Connect to existing browser via WebSocket
            const wsEndpoint: string = `ws://127.0.0.1:${browserPath.port}${browserPath.wsEndpoint}`;
            this.browser = await chromium.connectOverCDP(wsEndpoint);
            
            // Get the default context or create new one with just user agent
            const contexts: BrowserContext[] = this.browser.contexts();
            if (contexts.length > 0) {
                this.context = contexts[0];
            } else {
                // If profile fingerprint is available, use it; otherwise use a default user agent
                if (this.profileFingerprint && this.profileFingerprint.userAgent) {
                    this.context = await this.browser.newContext({
                        userAgent: this.profileFingerprint.userAgent.value
                    });
                } else {
                    // Use default user agent for existing profiles without fingerprint
                    this.context = await this.browser.newContext({
                        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    });
                }
            }
            
            // Use existing pages if reuseExistingPages is true and pages exist
            if (reuseExistingPages) {
                const pages: Page[] = this.context.pages();
                if (pages.length > 0) {
                    // Use the first existing page (already has content loaded by Dolphin)
                    this.page = pages[0];
                    this.log('Using existing page from Dolphin profile');
                } else {
                    // Create new page only if no pages exist
                    this.page = await this.context.newPage();
                    this.log('Created new page');
                }
            } else {
                // Always create new page (default behavior)
                this.page = await this.context.newPage();
            }
            
            // DO NOT manually set viewport - Dolphin Anty handles this based on screenMode='manual'
            // Setting viewport manually can create impossible configurations (inner > outer)
            // Let Dolphin control both window and viewport sizes for consistency
            
            // Verify dimensions to ensure Dolphin configured them correctly
            const actualDimensions = await this.page.evaluate(() => {
                return {
                    screen: {
                        width: window.screen.width,
                        height: window.screen.height,
                        availWidth: window.screen.availWidth,
                        availHeight: window.screen.availHeight
                    },
                    window: {
                        innerWidth: window.innerWidth,
                        innerHeight: window.innerHeight,
                        outerWidth: window.outerWidth,
                        outerHeight: window.outerHeight
                    }
                };
            });
            
            let screenWidth = 1920;
            let screenHeight = 1080;
            
            if (this.profileFingerprint) {
                screenWidth = this.profileFingerprint.screenWidth;
                screenHeight = this.profileFingerprint.screenHeight;
            }
            // Validate dimensions are realistic (inner must be <= outer)
            if (actualDimensions.window.innerWidth > actualDimensions.window.outerWidth ||
                actualDimensions.window.innerHeight > actualDimensions.window.outerHeight) {
                this.log(`⚠️ WARNING: Viewport larger than window - this will trigger anti-bot!`);
            }
            
            // Initialize human interactions with the page
            this.humanInteractions = new HumanInteractions(this.page);

           
            return true;
        } catch (error: any) {
            console.error(' Failed to initialize Playwright:', error.message);
            throw error;
        }
    }

    async loadUserData(userIndex: number | null = null, type: 'entry' | 'account' | 'entry-queuepass' = 'entry'): Promise<UserData | null> {
        try {
            
            // If currentUser is already set (from bulk processing), use it
            if (this.currentUser) {
                // this.log(`Using pre-loaded user: ${this.currentUser.EMAIL}`);
                //this.csvHelper.printUserInfo(this.currentUser);
                // Generate address data if not already generated
                if (!this.generatedAddress) {
                    this.generatedAddress = await UtilityHelper.generateAddressData(this.currentUser, 3, this.log.bind(this), type);
                }

                
                return this.currentUser;
            }
            
            // Read CSV data if not already loaded
            if (this.csvHelper.getUserCount() === 0) {
                await this.csvHelper.readCsvData(false);
            }

            // Get user data
            let user: UserData | null;
            if (userIndex !== null) {
                user = this.csvHelper.getUserByIndex(userIndex) as UserData;
            } else {
                user = this.csvHelper.getNextUser() as UserData | null;
            }

            if (!user) {
                this.log('No user data available', 'error');
                return null;
            }

            // Task number is already set in startFifaAutomation

            // Validate user data
            const validation: any = this.csvHelper.validateUser(user);
            if (!validation.isValid) {
                this.log(`Invalid user data: ${JSON.stringify(validation)}`, 'error');
                return null;
            }

            this.currentUser = user;
            
            // Generate address data based on user's FAN_OF country
            this.generatedAddress = await UtilityHelper.generateAddressData(user, 3, this.log.bind(this));
            
            this.csvHelper.printUserInfo(user);
            
            return user;
        } catch (error: any) {
            this.log(`Error loading user data: ${error.message}`, 'error');
            return null;
        }
    }

    async detect_update_profile(): Promise<boolean> {
        try{
            if (!this.humanInteractions || !this.currentUser || !this.page) {
                throw new Error('HumanInteractions or currentUser not initialized');
            }
    
            // if div[class="auth-content-form-title"], first h1 contains Update Profile
            const updateProfileElement = await this.page?.locator('div[class="auth-content-form-title"]').first();
            if (await updateProfileElement?.isVisible()) {
                const updateProfileMessageText = await updateProfileElement?.textContent();
                if (updateProfileMessageText && updateProfileMessageText.includes('Update Profile')) {
                    return true;
                    
                }
            }
            return false;
        }catch(error: any){
            this.log('Error detecting update profile, reason:', error);
            return false;
        }
    }

    async fifa_update_profile(): Promise<boolean> {
        try{
            if (!this.humanInteractions || !this.generatedAddress || !this.currentUser) {
                throw new Error('Required data not initialized');
            }

            this.log('Update profile needed, continuing...');
            // fill lastname
            const lastnameFillResult: boolean = await this.humanInteractions.robustFill('input[id="lastname"]', this.generatedAddress?.LAST_NAME || '', 'Last name', null, 3, 60, this.log.bind(this));
            if(!lastnameFillResult){
                throw new Error('Failed to fill last name');
            }
            // now we submit the form again
            const submitUpdateProfileResult: boolean = await this.humanInteractions.robustClick('button[id="btnSubmitProfile"]', 'Submit profile update', null, 3, 60, this.log.bind(this));
            if(!submitUpdateProfileResult){
                throw new Error('Failed to submit update profile');
            }
            return true;
        }catch(error: any){
            this.log('Error updating profile, reason:', error);
            return false;
        }
    }
  
    

    /*
        START: fifa ticket page with learn more button to go to login
        END: Logged in (existing account or created new one)
    */
    async fifa_login(submitLock?: { acquire: () => Promise<() => void> }): Promise<boolean> {
        try{
            if (!this.humanInteractions || !this.currentUser || !this.page) {
                throw new Error('HumanInteractions or currentUser not initialized');
            }
            
            /* 1. Fill email */
            const fillEmailResult: boolean = await this.humanInteractions.robustFill(
                'input[name="email"]', 
                this.currentUser.EMAIL, 
                'Email',
                null, 
                3, 
                60, 
                this.log.bind(this),
            );
            if(!fillEmailResult){
                throw new Error('Failed to fill email field');
            }
            
            // Human pause + cursor movement between fields (800-1800ms)
            await this.page.waitForTimeout(this.humanInteractions.randomDelay(800, 1200));
            await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(600, 1000));
            
            const fillPasswordResult: boolean = await this.humanInteractions.robustFill(
                'input[name="password"]', 
                this.currentUser.PASSWORD, 
                'Password',
                null, 
                3, 
                60, 
                this.log.bind(this),
            ); 
            if (!fillPasswordResult) {
                throw new Error('Failed to fill password field');
            }

            // Human pause before clicking button - hesitation/review (1200-2500ms)
            this.log('Pausing before login submit (human hesitation)...');
            await this.page.waitForTimeout(this.humanInteractions.randomDelay(1200, 2500));
            
            // ACQUIRE LOCK BEFORE ANY BLOCKING OPERATIONS
            let releaseLock: (() => void) | undefined;
            if (submitLock) {
                this.log('Waiting for submit lock (login)...');
                releaseLock = await submitLock.acquire();
                this.log('Submit lock acquired for login');
            }
            
            // Small cursor movement near button before clicking (checking button)
            // Wrapped in try-catch to prevent hanging
            try {
                await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(500, 800));
            } catch (err) {
                this.log(`⚠️  randomIdleMovements failed: ${err}`, 'warn');
            }
            let submitError: any = undefined;
            try {
                // click login button
                const clickLoginButtonResult: boolean = await this.humanInteractions.robustClick(
                    'button[id="loginFormSubmitBtn"]', 
                    'Login button', 
                    null, 
                    3, 
                    60, 
                    this.log.bind(this),
                ); 
                if(!clickLoginButtonResult){
                    throw new Error('Failed to click login button');
                }
            } catch (err) {
                submitError = err;
                this.log(`Error during login submit: ${err}`, 'error');
            } finally {
                // CRITICAL: ALWAYS wait 3-4 seconds before releasing lock, even on error
                // This prevents race conditions and maintains consistent timing
                if (releaseLock) {
                    try {
                        this.log('Waiting 1.5-4 seconds before releasing login lock...');
                        // Increase lower bound to 1500ms to create slightly longer, less predictable locks
                        await this.page.waitForTimeout(this.humanInteractions.randomDelay(1500, 4000));
                    } catch (waitError: any) {
                        this.log(`Error during lock wait: ${waitError.message}`, 'warn');
                    }
                    
                    this.log('🔒 Releasing submit lock for login');
                    releaseLock();
                }
                
                // Re-throw the error after lock is released
                if (submitError) {
                    throw submitError;
                }
            }

            // Wait after submit (humans wait for response)
            await this.page.waitForTimeout(this.humanInteractions.randomDelay(1500, 2500));
            // check "user is not found message"
            /*<div id="error-container" data-handlepopup="true" class="inputErrorMsgContainer form"><div class="inputErrorMsg" data-skvisibility="" data-skcomponent="skerror" id="error-div">User not found</div></div> */
            // check if this error message is visible, if its really "user not found" throw error
            // Check for "User not found" error - simple 3 attempts with 1 second between
            let userNotFoundFound = false;
            let updateProfileNeeded = false;
            for (let i = 0; i < 3; i++) {
                try {
                    const errorElement = await this.page?.locator('div[id="error-container"]').first();
                    if (await errorElement?.isVisible()) {
                        const userNotFoundMessageText = await errorElement?.textContent();
                        if (userNotFoundMessageText && userNotFoundMessageText.includes('User not found')) {
                            this.log('User not found, switching to registration');
                            return await this.fifa_register(submitLock);
                        }
                        // If error exists but doesn't contain "User not found", just continue
                    }

                    // if div[class="auth-content-form-title"], first h1 contains Update Profile
                    const updateProfileElement = await this.page?.locator('div[class="auth-content-form-title"]').first();
                    if (await updateProfileElement?.isVisible()) {
                        const updateProfileMessageText = await updateProfileElement?.textContent();
                        if (updateProfileMessageText && updateProfileMessageText.includes('Update Profile')) {
                            updateProfileNeeded = true;
                            break;
                        }
                    }
                } catch (error) {
                    // Ignore errors, just continue checking
                }
                
                // Wait 1 second before next attempt (except on last attempt)
                if (i < 2) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }

            if(updateProfileNeeded){
               let updateProfileResult = await this.fifa_update_profile();
               if(!updateProfileResult){
                    throw new Error('Failed to update profile');
               }
            }

            // now BEFOREE continue, check if the update profile message is no longer visible, else it triggers AGAIN
            // check for 5 seconds if its still needed if its not we can continue
           
            for(let i = 0; i < 15; i++){
                await this.page?.waitForTimeout(1000);
                const updateProfileNeeded = await this.detect_update_profile();
                if(!updateProfileNeeded){
                    break;
                }
            }   


            // If we get here, no "User not found" error was detected - login successful
            return true;
        }catch(error: any){
            // Handle proxy timeout specifically
            if (error.message && error.message.includes('PROXY_TIMEOUT')) {
                this.log(`Proxy timeout during login attempt: ${error.message}`);
                throw error; // Re-throw to trigger proxy retry
            }
            
            this.log(`Login error: ${error.message}`);
            return false;
        }
    }
    async fifa_register(submitLock?: { acquire: () => Promise<() => void> }, type: 'entry' | 'account' | 'entry-queuepass' = 'entry'): Promise<boolean> {
        try{
            if (!this.humanInteractions || !this.generatedAddress || !this.currentUser) {
                throw new Error('Required data not initialized');
            }
            // Head to register
            if(type === 'entry'){
                const clickRegisterButtonResult: boolean = await this.humanInteractions.robustClick('button[id="registerBtn"]', 'Register button', null, 3, 60, this.log.bind(this), 'default', false, true); 
                if(!clickRegisterButtonResult){
                    throw new Error('Failed to click register button');
                }
            }
           

            // Fill register form
            const registerFillResult: boolean = await registerFill(this.humanInteractions as any, this.generatedAddress as any, this.currentUser as any, this.log.bind(this), submitLock, type);
            if(!registerFillResult){
                throw new Error('Failed to fill register form');
            }


            // Check for EITHER account error OR password form - whichever comes first
            let cancelled = false;
            
            const accountErrorPromise = this.humanInteractions.waitForElementRobust('div[class="inputErrorMsg"]', 'Account error message', null, 30, (msg) => {
                if (!cancelled) this.log(msg);
            });
            
            const passwordFormPromise = this.humanInteractions.waitForElementRobust('form[id="frmRegister2"]','Password form', null, 30, (msg) => {
                if (!cancelled) this.log(msg);
            });

            const result = await Promise.race([
                accountErrorPromise.then(result => {
                    cancelled = true;
                    return { type: 'error', result };
                }),
                passwordFormPromise.then(result => {
                    cancelled = true;
                    return { type: 'form', result };
                })
            ]);

            // Check if it was the account error that won
            if(result.type === 'error' && result.result === true){
                // Check if account error exists
                const errorElements = this.page?.locator('div[class="inputErrorMsg"]');
                const errorCount = await errorElements?.count() || 0;
                
                if(errorCount > 0){
                    for(let i = 0; i < errorCount; i++){
                        const errorText = await errorElements?.nth(i).textContent();
                        if(errorText && (errorText.includes('already exists') || errorText.includes('User already exists'))){
                            // update csv to mark as account created
                            await this.csvHelper.markAccountCreated(this.currentUser.EMAIL);
                            this.log('Account already exists, logging in', 'error');
                            const clickLoginButtonResult: boolean = await this.humanInteractions.robustClick('button[data-skbuttonvalue="frmLogin"]', 'Login button', null, 3, 60, this.log.bind(this));
                            if(!clickLoginButtonResult){
                                throw new Error('Failed to click login button');
                            }
                            // wait 2-3 seconds
                            await new Promise(resolve => setTimeout(resolve, UtilityHelper.randomDelay(2000, 3000)));
                            
                            return await this.fifa_login();
                        }
                    }
                }
            }

            // If we get here, password form was found
            if(result.type === 'form' && result.result === true){
                this.log('Password form found, continuing registration');
            } else {
                throw new Error("LOGIN_BLOCKED");
            }

            // if password form is not found, we are blocked
            if(result.type !== 'form'){
                this.log('Password form not found, stopping task...');
                
            }

            // Human delay: Read password requirements (1-2 seconds)
            this.log('Simulating reading password requirements...');
            await this.page?.waitForTimeout(this.humanInteractions.randomDelay(1000, 2000));
            await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(500, 800));

            const passwordInput1Visible: boolean = await this.humanInteractions.robustFill('input[id="password"]', this.currentUser.PASSWORD, 'Password', null, 3, 60, this.log.bind(this));
            if(!passwordInput1Visible){
                throw new Error('Failed to fill password input 2');
            }

            // Human pause between password fields (900-1500ms + cursor movement)
            await this.page?.waitForTimeout(this.humanInteractions.randomDelay(900, 1500));
            await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(400, 700));

            const passwordInput2FillResult: boolean = await this.humanInteractions.robustFill('input[id="confirm-password"]', this.currentUser.PASSWORD, 'Password', null, 3, 60, this.log.bind(this));
            if(!passwordInput2FillResult){
                throw new Error('Failed to fill password input 2');
            }

            // Human pause before T&C (1200-2000ms - users read T&C... or pretend to)
            this.log('Simulating reading Terms & Conditions...');
            await this.page?.waitForTimeout(this.humanInteractions.randomDelay(1200, 2000));
            await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(500, 800));

            // click terms and service
            const clickTandC: boolean = await this.humanInteractions.robustClick('input[name="TandC"]', 'Terms and service', null, 3, 60, this.log.bind(this)); 
            if(!clickTandC){
                throw new Error('Failed to click terms and service');
            }
            
            // Human pause before submit (1500-2500ms - final review before submitting)
            this.log('Final review before submitting registration...');
            await this.page?.waitForTimeout(this.humanInteractions.randomDelay(1500, 2500));
            
            // ACQUIRE LOCK BEFORE ANY BLOCKING OPERATIONS
            let releaseLock: (() => void) | undefined;
            if (submitLock) {
                this.log('Waiting for submit lock (registration)...');
                releaseLock = await submitLock.acquire();
                this.log('Submit lock acquired for registration');
            }
            
            // Small cursor movement near button before clicking (checking button)
            // Wrapped in try-catch to prevent hanging
            try {
                await this.humanInteractions.randomIdleMovements(this.humanInteractions.randomDelay(600, 1000));
            } catch (err) {
                this.log(`⚠️  randomIdleMovements failed: ${err}`, 'warn');
            }
            let submitError: any = undefined;
            try {
                // Click create account button
                const clickCreateAccountButtonResult: boolean = await this.humanInteractions.robustClick('button[id="btnSubmitRegister"]', 'Create account button', null, 3, 60, this.log.bind(this));
                if(!clickCreateAccountButtonResult){
                    throw new Error('Failed to click create account button');
                }
                
                // Wait after submit (humans wait for response)
                await this.page?.waitForTimeout(this.humanInteractions.randomDelay(1500, 2500));
            } catch (err) {
                submitError = err;
                this.log(`Error during registration submit: ${err}`, 'error');
            } finally {
                // CRITICAL: ALWAYS wait 3-4 seconds before releasing lock, even on error
                // This prevents race conditions and maintains consistent timing
                if (releaseLock) {
                    try {
                        this.log('Waiting 3-4 seconds before releasing registration lock...');
                        await this.page?.waitForTimeout(this.humanInteractions.randomDelay(3000, 4000));
                    } catch (waitError: any) {
                        this.log(`Error during lock wait: ${waitError.message}`, 'warn');
                    }
                    
                    this.log('🔒 Releasing submit lock for registration');
                    releaseLock();
                }
                
                // Re-throw the error after lock is released
                if (submitError) {
                    throw submitError;
                }
            }
            
            // Mark account as created in CSV
            await this.csvHelper.markAccountCreated(this.currentUser.EMAIL);
            this.log(`Account created and marked in CSV: ${this.currentUser.EMAIL}`);
        
            return true;
            

        }catch(error: any){
            console.log(error)
            return false;
        }
    }

  


    async fifa_check_page_result(type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry'): Promise<string> {
        try{
        if (!this.page) {
            throw new Error('Page not initialized');
        }
        // We need to check for email verification page, account completion page, draw entry page and login blocked
        // email elements
        const emailElements: string[] = ['div[class="verify-content-form"]', 'input[placeholder="Enter Code"]', 'input[id="otp"]']

        // login blocked elements
        const loginBlockedElements: string[] = ['div[class="auth-container"]','div[class="auth-image-content-container"]']

        // TODO fix these elements 
        // account completion elements
        const accountCompletionElements: string[] = ['input[id="address_line_1"]']
        // draw entry elements
        const drawEntryElements: string[] = ['button[aria-label="Enter Draw"]']


        // TODO check these selectors
        const drawEntryCompletedElements: string[] = ['button[aria-label="Cancel entry"]']
        

        // check if any of the elements are visible
        for(let i = 0; i < emailElements.length; i++){
            const emailElementVisible: boolean = await this.page.locator(emailElements[i]).isVisible();
            if(emailElementVisible){
                return 'EMAIL_VERIFICATION';
            }
        }
        // check if update profile is needed
        const updateProfileNeeded = await this.detect_update_profile();
        if(updateProfileNeeded){
            return 'UPDATE_PROFILE_NEEDED';
        }
        for(let i = 0; i < loginBlockedElements.length; i++){
            const loginBlockedElementVisible: boolean = await this.page.locator(loginBlockedElements[i]).isVisible();
            if(loginBlockedElementVisible){
                return 'LOGIN_BLOCKED';
            }
        }
        for(let i = 0; i < accountCompletionElements.length; i++){
            const accountCompletionElementVisible: boolean = await this.page.locator(accountCompletionElements[i]).isVisible();
            if(accountCompletionElementVisible){
                return 'ACCOUNT_COMPLETION_PAGE';
            }
        }
        for(let i = 0; i < drawEntryElements.length; i++){
            const drawEntryElementVisible: boolean = await this.page.locator(drawEntryElements[i]).isVisible();
            if(drawEntryElementVisible){
                return 'DRAW_ENTRY_PAGE';
            }
        }
        for(let i = 0; i < drawEntryCompletedElements.length; i++){
            const drawEntryCompletedElementVisible: boolean = await this.page.locator(drawEntryCompletedElements[i]).isVisible();
            if(drawEntryCompletedElementVisible){
                return 'DRAW_COMPLETED_PAGE';
            }
        }
        // if url is https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets
        if(this.page.url().includes('https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets') && type === 'account'){
            return 'ACCOUNT_COMPLETED_PAGE';
        }
       
        return 'UNKNOWN';
        
        }catch(error: any){
            console.log(error)
            return 'UNKNOWN';
        }
       
    }
    async fifa_handle_queue(): Promise<void> {
        try{
            const settingsHelper = SettingsHelper.getInstance();
            const capsolverKey = settingsHelper.get('CAPSOLVER_KEY');   
            if(capsolverKey === null || capsolverKey === ''){
                throw new Error('CAPSOLVER_KEY not set');
            }
            const queueHandleResult = await queueHandler(this.humanInteractions as any, this.page, capsolverKey, this.log.bind(this));

            if(queueHandleResult === 'PROXY_TIMEOUT'){
                throw new Error('PROXY_TIMEOUT');
            }
            else if(queueHandleResult === 'PASSED_QUEUE'){
                this.log('Queue passed, entering draw...');
                // continue with entry flow
            }
        }catch(error: any){
            this.log('Error handling queue, reason:', error)
            throw new Error('Failed to handle queue');
        }
    }
    async fifa_email_verification(): Promise<boolean | string> {
        try{
        if (!this.imapHelper || !this.currentUser || !this.humanInteractions) {
            throw new Error('Required dependencies not initialized');
        }
        
        // Handle imap global connection with imap and
            // Look for fifa email for 60 seconds every 10 seconds
            const startTime: number = Date.now();
            let emailCode: string | null = null;

            // Use RECEIVINGEMAIL if available, otherwise fall back to EMAIL
            const receivingEmail = this.currentUser.RECEIVINGEMAIL || this.currentUser.EMAIL;
            const accountEmail = this.currentUser.EMAIL;
            this.log(`Searching for FIFA mail for account: ${accountEmail} (receiving at: ${receivingEmail})`);

            while((Date.now() - startTime) < 180000){
                // wait 5 seconds before retrying
                await new Promise(resolve => setTimeout(resolve, 5000));
                
                // Connect to IMAP right before searching
                this.log('Connecting to IMAP for OTP search...');
                await this.imapHelper.connect();
                
                emailCode = await this.imapHelper.searchForFifaEmail(receivingEmail, accountEmail, this.log.bind(this));
                
                // Disconnect from IMAP immediately after searching
                this.log('Disconnecting from IMAP...');
                await this.imapHelper.disconnect();
                
                if(emailCode){
                    this.log(`OTP received: ${emailCode}`);
                    break;
                }
            }
            
            if(!emailCode){
                await sendErrorNotification(this.currentUser, 'Failed to get OTP, check forwarding', this.log.bind(this));
                return "IMAP_FAILURE";
            }else{
                //this.log(`FIFA email received: ${emailCode}`);
            }

             // Check and fill otp form
            const otpForm: boolean = await this.humanInteractions.robustFill('input[id="otp"]', emailCode, 'OTP input', null, 3, 60, this.log.bind(this));
            if(!otpForm){
                throw new Error('ELEMENT_FILL_FAILURE');
            }

            // Now there are 2 different types of submit buttons, first look and find which one there is for 15 seconds if not found throw error
            const submitButtons: string[] = ['button[id="auto-submit"]', 'button[id="loginFormSubmitBtn"]']

            let correctSelector: string | null = null;


            for(let i = 0; i < 15; i++){
                for(let selector of submitButtons){
                    const submitButtonVisible: boolean = await this.page?.locator(selector).isVisible() || false;
                    if(submitButtonVisible){
                        correctSelector = selector;
                        break;
                    }
                }
                
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            if(!correctSelector){
                throw new Error('ELEMENT_NOT_FOUND');
            }
            const otpSubmitResult: boolean = await this.humanInteractions.robustClick(correctSelector, 'OTP submit button', null, 3, 60, this.log.bind(this));
            if(!otpSubmitResult){
                throw new Error('ELEMENT_CLICK_FAILURE');
            }
            // wait 5 seconds

            await new Promise(resolve => setTimeout(resolve, 5000));

            // Now we need to check if this was successful
            // check 5 times with 3 seconds in between, if it stays login result email verif it failed  
            for(let i = 0; i < 5; i++){
                await new Promise(resolve => setTimeout(resolve, 3000));
                const loginResult: string = await this.fifa_check_page_result();
                if(loginResult !== 'EMAIL_VERIFICATION'){
                    // Mark account as verified in CSV
                    await this.csvHelper.markAsVerified(this.currentUser.EMAIL);
                    this.log(`Account verified and marked in CSV: ${this.currentUser.EMAIL}`);
                    return true;
                }
            }

            // If we are here, we are still on email verification page
            this.log('Still on email verification page, retrying...');
            return false;
         
        }catch(error: any){
            throw error;
        }
    }
  
    async fifa_navigate_auth(method: string = 'learn_more'): Promise<void> {
        try{
            if (!this.humanInteractions || !this.page || !this.context) {
                throw new Error('Required dependencies not initialized');
            }

            /* 1. Close popup and cookie banner BEFORE clicking buttons */
            if(method !== 'learn_more'){
                this.log('Checking for popup overlay...');
                const closePopup = await this.humanInteractions.robustClick(
                    '[class*="pop-up_closeIcon"]',
                    'FIFA Store popup close button', 
                    this.page,
                    3,
                    10,
                    this.log.bind(this),
                    'stabilize',
                    false
                );
                if(!closePopup){
                    this.log('No popup found or failed to close, continuing...')
                } else {
                    this.log('Popup closed successfully');
                }
            }

            if(this.currentUser?.ADDRESS_COUNTRY === 'USA'){
                const cookieBannerResult: boolean = await this.humanInteractions.robustClick(
                    '#onetrust-accept-btn-handler', 
                    'Cookie banner', 
                    this.page,
                    3,
                    30,
                    this.log.bind(this),
                    'stabilize',
                    false
                );
                if(!cookieBannerResult){
                    this.log('Failed to accept cookie banner, continuing...')
                }else{
                    this.cookieBannerAccepted = true;
                    this.log('Cookie banner accepted');
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
            }
           
            /* 2. Navigate to login/register page */
            if(method === 'learn_more'){
                const clickLearnMoreResult: boolean = await this.humanInteractions.robustClick(
                    'a[href*="fifa-fwc26-us.tickets.fifa.com"]', 
                    'Learn more button', 
                    null,
                    3,
                    60,
                    this.log.bind(this)
                ); 
                if (!clickLearnMoreResult) {
                    throw new Error('Failed to click Learn more button');
                }
              

            }else if(method === 'sign_in_button'){
                this.log('Clicking "My Account" button for sign in...');
                const clickProfile: boolean = await this.humanInteractions.robustClick(
                    'button[aria-label="My Account"]', 
                    'Profile button',
                    null,
                    3,
                    60,      
                    this.log.bind(this)
                ); 
                if (!clickProfile) {
                    throw new Error('Failed to click Profile button');
                }
                this.log(' Profile button clicked, waiting for dropdown...');
                await this.page.waitForTimeout(2000);
                this.log('Clicking "Sign In" link...');
                const clickSignInButton: boolean = await this.humanInteractions.robustClick(
                    'a[label="Sign In"]', 
                    'Sign in button',
                    null,
                    3,
                    60,
                    this.log.bind(this)
                ); 
                if(!clickSignInButton){
                    throw new Error('Failed to click Sign in button');
                }
            }else if(method === 'register_button'){
                this.log('Clicking "My Account" button for registration...');
                const clickProfile: boolean = await this.humanInteractions.robustClick(
                    'button[aria-label="My Account"]', 
                    'Profile button',
                    null,
                    3,
                    60,      
                    this.log.bind(this)
                ); 
                if (!clickProfile) {
                    throw new Error('Failed to click Profile button');
                }
                this.log(' Profile button clicked, waiting for dropdown...');
                await this.page.waitForTimeout(2000);
                this.log('Clicking "Sign Up" link...');
                const clickSignUpButton: boolean = await this.humanInteractions.robustClick(
                    'a[label="Sign Up"]', 
                    'Sign up button',
                    null,
                    3,
                    60,
                    this.log.bind(this)
                ); 
                if(!clickSignUpButton){
                    throw new Error('Failed to click Sign up button');
                }


            }
           
            await this.page.waitForTimeout(UtilityHelper.randomDelay(2000, 5000));

            // Robust page detection with retry mechanism
            const pageDetectionSuccess = await this.humanInteractions.detectAndSwitchToNewPage(this.context, this.log.bind(this));
            if (!pageDetectionSuccess) {
                this.log('Failed to detect login redirect after retries, restarting flow...', 'error');
                throw "PROXY_TIMEOUT";
            }
            
            // Update the page reference after successful detection
            this.page = this.humanInteractions.page;
            
            // now wait till dom content of login page is loaded
            if (this.page) {
                await this.page.waitForLoadState('domcontentloaded', { timeout: 60000 });
            }
            // we need to check if we acctually are on the auth.fifa.com page
            // first dom content loaded
            await this.page?.waitForLoadState('domcontentloaded', { timeout: 60000 });

            // now we check and want to be on the auth.fifa.com page for at least 2 secodns in a row
            let isOnAuthPageCounter = 0;
            let isOnQueuePageCounter = 0;
            for(let i = 0; i < 25; i++){
                const currentUrl: string = await this.page?.url() || '';
                if(currentUrl.includes('auth.fifa.com')){
                    isOnAuthPageCounter++;
                }else if(currentUrl.includes('/pkpcontroller/') && currentUrl.includes('queue')){
                    isOnQueuePageCounter++;
                }
                if(isOnAuthPageCounter >= 5 || isOnQueuePageCounter >= 5){
                    break;
                }
                await this.page?.waitForTimeout(1000);
            }
            // on auth page, we just ocntinue, but if on queue we need to HANDLE the queu
            if(isOnQueuePageCounter >= 5){
                this.log('Queue detected, handling queue...');
                // we need to handle the queue
                await this.fifa_handle_queue();
                // wait domcontentloaded here
                await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });
            }
            /* 3. Accept cookie banner on auth page if not already accepted */   
            if(!this.cookieBannerAccepted){
                this.log('Checking for cookie banner on auth page...');
                const cookieBannerResult: boolean = await this.humanInteractions.robustClick(
                    '#onetrust-accept-btn-handler', 
                    'Cookie banner', 
                    this.page,
                    3,
                    60,
                    this.log.bind(this),
                    'stabilize',
                    false
                );
                if(!cookieBannerResult){
                    this.log('Failed to accept cookie banner, continuing...')
                }
            }
        }catch(error: any){
            this.log('Error navigating to auth, reason:', error)
            throw "PROXY_TIMEOUT"

        }

    }

    async queueLoopFlow(threads: number): Promise<void> {

    }


  


    async initFifaFlow(
        taskData: UserData, 
        taskNumber: number, 
        proxies: string[], 
        imapHelper: any,
        startUrl: string = 'https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets',
        type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry',
        totalAmountOfTasks: number = 0,
        submitLock?: { acquire: () => Promise<() => void> },
        queuePassCookie: string | null = null
    ): Promise<boolean | string> {
        try {
            this.taskNumber =  taskNumber - 1 !== null ?  taskNumber - 1 + 1 : 1;
            this.currentUser = taskData;
            this.proxies = proxies;
            this.imapHelper = imapHelper;
            this.isRunning = true;

            // Create Dolphin profile with retry mechanism
            this.log(`Starting profile creation for task ${this.taskNumber}...`);
            const profileResult: ProfileResult | string | boolean = await this.profileHelper.createAndStartProfile(this.proxies, this.taskNumber, this.log.bind(this), 3);
            
            if (profileResult === 'NO_PROXIES_AVAILABLE') {
                this.log('No unused proxies available - stopping processing', 'error');
                return 'NO_PROXIES_AVAILABLE';
            } else if (!profileResult) {
                this.log('Failed to create and start profile after retries', 'error');
                return 'PROFILE_CREATION_FAILED';
            }

            this.profileFingerprint = (profileResult as ProfileResult).profileData;
            this.log(`Profile created and started successfully: ${this.profileHelper.getProfileId()}`);

            // Initialize browser with retry mechanism
            let browserInitSuccess = false;
            for (let attempt = 1; attempt <= 3; attempt++) {
                try {
                    this.log(`Initializing browser... (Attempt ${attempt}/3)`);
                    browserInitSuccess = await this.browserInit();
                    if (browserInitSuccess) {
                        this.log(`Browser initialized successfully on attempt ${attempt}`);
                        break;
                    }
                } catch (error: any) {
                    this.log(`Browser initialization attempt ${attempt} failed: ${error.message}`, 'warn');
                    if (attempt < 3) {
                        const waitTime = 2000 * attempt; // 2s, 4s, 6s
                        this.log(`Waiting ${waitTime}ms before retry...`);
                        await new Promise(resolve => setTimeout(resolve, waitTime));
                    }
                }
            }

            if (!browserInitSuccess) {
                // Clean up profile before throwing error
                try {
                    await this.profileHelper.deleteProfile(this.log.bind(this));
                } catch (cleanupError: any) {
                    console.error('Error deleting profile after browser init failure:', cleanupError.message);
                }
                throw new Error('Failed to initialize browser after retries');
            }

            await this.csvHelper.readCsvData(false);

            /* REPLACE STUFF START */
            const user: UserData | null = await this.loadUserData(this.taskNumber, type === 'entry-fifa-com' || type === 'entry-queuepass' ? 'entry' : type);
            if (!user) {
                throw new Error('Failed to load user data');
            }

            // cuz login only, entered draw = success
            const entryFlowResult: string  = await this.entryFLOW(startUrl, type, submitLock, queuePassCookie);
            switch(entryFlowResult){
                case "ENTERED_DRAW":

                    if(type === 'account'){
                        this.log(`Successfully created account ${this.currentUser?.EMAIL}`, 'success');
                        await sendAccountCreationNotification(this.currentUser as UserData, this.log.bind(this));
                    }else if(type === 'entry' || type === 'entry-fifa-com' || type === 'entry-queuepass'){
                        this.log(`Successfully entered draw ${this.currentUser?.EMAIL}`, 'success');
                        // update csv with entered draw
                        await this.csvHelper.markEntryCompleted(this.currentUser?.EMAIL);
                        await sendDrawEntryNotification(this.currentUser as UserData, this.log.bind(this));
                    }else{
                        throw new Error('Invalid type');
                    }
                    break;
                // dont restart on imap failure, will yield same result
                case "IMAP_FAILURE":
                    // if FLAG_OTP_ISSUES setting is true, we update this in csv
                    const settingsHelper = SettingsHelper.getInstance();
                    if(settingsHelper.shouldFlagOtpIssues()){
                        await this.csvHelper.flagOtpIssues(this.currentUser?.EMAIL || '');
                    }
                    this.log('IMAP failure, stopping task...');
                    break;
                // dont restart on login blocked, will yield same result
                case "LOGIN_BLOCKED":
                    this.log('Login blocked, stopping task...');
                    break;
                case "PROXY_TIMEOUT":
                    this.log('Proxy timeout, restarting draw entry...');
                    // delete profile and run initFifaFlow again
                    this.retryCount++;
                    if(this.retryCount > this.maxRetries){
                        this.log('Max retries reached, stopping task...');
                        return "MAX_RETRIES";
                    }
                    
                    // CRITICAL: Ensure profile is properly cleaned up before retry
                    try {
                        // Add timeout to cleanup to prevent hanging
                        const cleanupPromise = Promise.all([
                            this.profileHelper.stopProfile(this.log.bind(this)),
                            this.profileHelper.deleteProfile(this.log.bind(this), true)
                        ]);
                        
                        const timeoutPromise = new Promise((_, reject) => {
                            setTimeout(() => reject(new Error('Cleanup timeout')), 15000); // 15 second timeout
                        });
                        
                        await Promise.race([cleanupPromise, timeoutPromise]);
                    } catch (cleanupError: any) {
                        this.log(`Error during profile cleanup before retry: ${cleanupError.message}`, 'warn');
                    }
                    
                    // shift proxies array to BEHIND the task amount
                    let shiftedProxies: string[] = this.proxies.slice(this.taskNumber % totalAmountOfTasks);
                    shiftedProxies.push(...this.proxies.slice(0, this.taskNumber % totalAmountOfTasks));
                    return await this.initFifaFlow(this.currentUser as UserData, this.taskNumber, shiftedProxies, this.imapHelper, startUrl, type, totalAmountOfTasks, submitLock);
            }

            // cleanup profile & return "result" for the task handler
            await this.profileHelper.deleteProfile(this.log.bind(this));
            
            return entryFlowResult;
            
        } catch (error: any) {
            this.log(`Unhandled error in fifa process stopping task: ${error.message}`, 'error');
            
            // Always cleanup on error
            try {
                await this.profileHelper.deleteProfile(this.log.bind(this));
            } catch (cleanupError: any) {
                this.log(`Error during cleanup: ${cleanupError.message}`, 'warn');
            }
            
            // Return specific error codes instead of throwing
            if (error.message.includes('Browser path not available')) {
                return 'PROFILE_START_FAILED';
            } else if (error.message.includes('Failed to create and start profile')) {
                return 'PROFILE_CREATION_FAILED';
            } else if (error.message.includes('Failed to initialize browser')) {
                return 'BROWSER_INIT_FAILED';
            }
            
            return 'UNKNOWN_ERROR';
        }
    }

    // Expose the proxy string used by this task (assigned during profile creation)
    getActiveProxyString(): string | null {
        return this.profileHelper.getLastAssignedProxyString();
    }

    async fifa_navigateToDraw(): Promise<boolean> {
        try{
            this.log('Navigating to draw...');
            await this.humanInteractions?.robustClick('li[name="PRE_SALES_WAITING_LIST"]', 'Draw button', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;

            let navigateToDrawSuccess: boolean = false;
            for(let i = 0; i < 10; i++){
                const currentUrl: string = await this.page?.url() || '';
                if(currentUrl.includes('https://fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications')){
                    navigateToDrawSuccess = true;
                    break;
                }
                await this.page?.waitForTimeout(1000);
            }
            if(!navigateToDrawSuccess){
                // navigate to draw via url
                const result = await this.humanInteractions?.browser_navigate('https://fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications', this.log.bind(this));
                if(!result){
                    return false;
                }
                navigateToDrawSuccess = true;
            }else{
                return true;

            }

            return false;
        }catch(error: any){
            this.log('Error navigating to draw, reason:', error)
            throw "PROXY_TIMEOUT"
        }
    }
   
    async fifa_address(): Promise<boolean> {
        try{
            this.log('Filling address form...');
            const addressFillResult = await addressFill(
                this.humanInteractions as any,
                this.page,
                this.generatedAddress as any,
                this.currentUser as any,
                this.log.bind(this)
            );
            if(!addressFillResult){
                throw new Error('Failed to fill address form');
            }

            // SUBMIT address form
            // a[id="save"]
            const submitAddressFormResult: boolean = await this.humanInteractions?.robustClick('a[id="save"]', 'Submit address form', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;
            if(!submitAddressFormResult){
                throw new Error('Failed to submit address form');
            }

            return true;

        }catch(error: any){
            this.log('Error filling address, reason:', error)
            throw "PROXY_TIMEOUT"
        }
    }
    async fifa_draw_entry(): Promise<boolean> {
        try{
            this.log('Entering draw...');
            // TODO CHECK IF ARIA LABEL IS SMART FOR OTHER LANGUAGES??
            // click enter draw button
            const enterDrawButton: boolean = await this.humanInteractions?.robustClick('button[aria-label="Enter Draw"]', 'Enter draw button', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;
            if(!enterDrawButton){
                throw new Error('Failed to enter draw');
            }

            // wait 3 seconds because css glithes TODO (better check)
            await this.page?.waitForTimeout(3000);

            const yesClickButton: boolean = await this.humanInteractions?.robustClick('button[class="yes-btn"]', 'Yes click button', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;
            if(!yesClickButton){
                throw new Error('Failed to click yes button');
            }

            const continueClickButton: boolean = await this.humanInteractions?.robustClick('button[aria-label="Continue"]', 'Continue click button', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;
            if(!continueClickButton){
                throw new Error('Failed to click continue button');
            }
            // wait 3 seconds
            await this.page?.waitForTimeout(3000);

            // Now we either detect that theres already a card added, or we add a card
            // check if we are on the correct page
            // search for div[class="stx-paymentSelection-container"] 
            const paymentSelectionContainer: boolean = await this.humanInteractions?.waitForElementRobust('.stx-paymentSelection-container', 'Payment selection container', null, 60, this.log.bind(this)) as boolean;
            if(!paymentSelectionContainer){
                throw new Error('Payment selection container not found');
            }

            // robust card add function that detects if card is already added and adds it if not
            const addCardResult: boolean = await addCard(this.humanInteractions as any, this.page, this.generatedAddress as GeneratedAddress, this.currentUser as any, this.log.bind(this));
            if(!addCardResult){
                throw new Error('Failed to add card');
            }

            // now card is added we need to click confimr checkbox and submit entry
            // input[id="stx-confirmation-terms-and-conditions"]
            const confirmCheckbox: boolean = await this.humanInteractions?.robustClick('input[id="stx-confirmation-terms-and-conditions"]', 'Confirm checkbox', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;
            if(!confirmCheckbox){
                throw new Error('Failed to click confirm checkbox');
            }

            // submit entry
            const submitEntryButton: boolean = await this.humanInteractions?.robustClick('button[aria-label="Submit Entry"]', 'Submit entry button', null, 2, 60, this.log.bind(this), 'default', false, true) as boolean;
            if(!submitEntryButton){
                throw new Error('Failed to click submit entry button');
            }
            return true;


        }catch(error: any){
            this.log('Error drawing entry, reason:', error)
            throw "PROXY_TIMEOUT"
        }
    }

    


    async fifa_completion(type: 'entry' | 'account' | 'entry-queuepass' = 'entry'): Promise<string> {
        try{
            let lastCompletionResult: string = 'UNKNOWN';
            let sameStatusInARow = 0;
            let completionResult: string = 'UNKNOWN';
        

            for (let i = 0; i < 7; i++) {
                completionResult = await this.fifa_check_page_result(type);
                // Dont instantly return login blocked or unknow cuz it can take a while to load
                if (completionResult !== 'UNKNOWN' && completionResult !== 'LOGIN_BLOCKED') break;
                await this.page?.waitForTimeout(5000);
            }

            if(completionResult === lastCompletionResult){
                sameStatusInARow++;
            }else{
                sameStatusInARow = 0;
            }
            lastCompletionResult = completionResult;

        
            if(sameStatusInARow > 3){
                return "PROXY_TIMEOUT";
            }


            switch(completionResult){
                case 'ACCOUNT_COMPLETED_PAGE':
                    await this.csvHelper.markAsVerified(this.currentUser?.EMAIL || '');
                    completionResult =  "ENTERED_DRAW";
                    break;
                case 'EMAIL_VERIFICATION':
                    // TODO BRING THIS BACKKK
                    //await this.csvHelper.markAccountCreated(this.currentUser?.EMAIL || '');
                    const emailVerificationResult: boolean | string = await this.fifa_email_verification();
                    if(emailVerificationResult === true){
                        //await this.csvHelper.markAsVerified(this.currentUser?.EMAIL || '');
                        if(type === 'account') {
                            completionResult = "ENTERED_DRAW";
                        }else if(type === 'entry'){
                            completionResult = "CONTINUE";
                        }
                    }
                    else if(emailVerificationResult === "IMAP_FAILURE"){
                        completionResult = "IMAP_FAILURE";
                    }else{
                        completionResult = "PROXY_TIMEOUT";
                    }
                    break;
                case 'UPDATE_PROFILE_NEEDED':
                    await this.fifa_update_profile();
                    completionResult = "CONTINUE";
                    break;
                case 'LOGIN_BLOCKED':
                    completionResult = "LOGIN_BLOCKED";
                    break;
                case 'ACCOUNT_COMPLETION_PAGE':
                    await this.fifa_address();
                    completionResult = "CONTINUE";
                    break;
                case 'HOME_PAGE':
                    await this.fifa_navigateToDraw();
                    completionResult = "CONTINUE";
                    break;

                case 'DRAW_ENTRY_PAGE':
                    await this.fifa_draw_entry();
                    completionResult = "CONTINUE";
                    break;
                case 'DRAW_COMPLETED_PAGE':
                    return "ENTERED_DRAW";
                default:
                    return "PROXY_TIMEOUT";
            }

            if(completionResult === "CONTINUE" && type === 'entry'){
                // wait 5 seconds before continuing
                await this.page?.waitForTimeout(5000);
                // wait for domcontentloaded here
                await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });
                return await this.fifa_completion(type);
            }
            return completionResult;
        }catch(error: any){
            this.log('Error in fifa_completion, reason:', error)
            throw "PROXY_TIMEOUT"
        }
    }

async IsDataDomeBlocked(): Promise<boolean> {
        try{
            if (!this.page) { return false; }
            // Look for the DataDome iframe
            const ddIframeCount: number = await this.page.locator('iframe[src*="geo.captcha-delivery.com"]').count();
            if (!ddIframeCount || ddIframeCount === 0) {
                return false;
            }

            // Find the frame by URL and check only the two specified selectors
            const frames = this.page.frames();
            const targetFrame = frames.reverse().find(f => f.url().includes('geo.captcha-delivery.com'));
            if (!targetFrame) {
                return false;
            }

            const robot = targetFrame.locator('div.captcha__robot').first();
            if (await robot.count() > 0 && await robot.isVisible().catch(() => false)) {
                return true;
            }

            const why = targetFrame.locator('p.captcha__robot__warning__why').first();
            if (await why.count() > 0 && await why.isVisible().catch(() => false)) {
                return true;
            }

            return false;
        }catch(error: any){
            this.log('Error detecting DataDome block, reason:', error)
            return false;
        }
    }

    async checkQueueStatus(): Promise<string> {
        try{
            let redirectToQueue = false;
                let ddBlockCount = 0;
                let queueCount = 0;
                const maxWaitTime = 30; // seconds
                const checkInterval = 1; // second
      
                
                for (let i = 0; i < maxWaitTime; i++) {
                    const currentUrl = await this.page?.url() || '';
                    
                    if (currentUrl.includes('auth.fifa.com')) {
                        this.log(`Queue pass valid - redirected to auth.fifa.com after ${i + 1}s`);
                        return 'PASSED_QUEUE';
                    }


                    if(currentUrl.includes('/pkpcontroller/') && currentUrl.includes('queue')){
                        queueCount++;
                        if(queueCount > 5){
                            return 'ON_QUEUE_PAGE';
                        }
                    }else{
                        queueCount = 0;
                    }

                    // detect DD blocks
                    let isDataDomeBlocked = await this.IsDataDomeBlocked();
                    if(isDataDomeBlocked){
                        ddBlockCount++;
                        if(ddBlockCount > 5){
                            return 'DATA_DOME_BLOCKED';
                        }
                    }else{
                        ddBlockCount = 0;
                    }
                    
                    // Log progress every 5 seconds
                    if (i > 0 && i % 5 === 0) {
                        this.log(`Still waiting for redirect... (${i}s/${maxWaitTime}s) - Current: ${currentUrl.substring(0, 60)}...`);
                    }
                    
                    await this.page?.waitForTimeout(checkInterval * 1000);
                }

                return 'PROXY_TIMEOUT';
        }catch(error: any){
            this.log('Error checking queue status, reason:', error)
            return 'PROXY_TIMEOUT';
        }
    }
    async handleQueuePass(maxRetry: number = 2, retyCount: number = 0): Promise<string> {
        try{
            if(retyCount >= maxRetry){
                return 'PROXY_TIMEOUT';
            }
            const queueStatus = await this.checkQueueStatus();
            if(queueStatus === 'ON_QUEUE_PAGE'){
                await this.fifa_handle_queue();
                return await this.handleQueuePass(maxRetry, retyCount + 1);
            }else if(queueStatus === 'DATA_DOME_BLOCKED'){
                return 'DATA_DOME_BLOCKED';
            }else if(queueStatus === 'PROXY_TIMEOUT'){
                return 'PROXY_TIMEOUT';
            }else{
                return 'PASSED';
            }
        }catch(error: any){
            this.log('Error handling queue pass, reason:', error)
            throw new Error('Failed to handle queue pass');
        }
    }

    async entryFLOW(
        startUrl: string = 'https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets',
        type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry',
        submitLock?: { acquire: () => Promise<() => void> },
        queuePassCookie: string | null = null
    ): Promise<string> {
        try{
            if (!this.humanInteractions) {
                throw new Error('HumanInteractions not initialized');
            }
            
            // Handle queue pass mode
            if (type === 'entry-queuepass' && queuePassCookie) {
                this.log('Queue Pass Mode: Injecting cookie first...');
                this.log(`Using queue pass cookie: ${queuePassCookie}`);
                if (this.context) {
                    await this.context.addCookies([{
                        name: 'AcpAT-v3-10-FWC26-LotteryFCFS',
                        value: queuePassCookie,
                        domain: '.fifa.com',
                        path: '/',
                        httpOnly: true,
                        secure: false
                    }]);
                    this.log('Queue pass cookie injected successfully');
                } else {
                    throw new Error('Browser context not initialized');
                }
                
                // Step 2: Navigate to the queue URL with the cookie
                this.log(`Step 2: Navigating to ${startUrl} with queue pass cookie...`);
                await this.humanInteractions.browser_navigate(startUrl, this.log.bind(this));
                
                // Wait for page load and potential redirects
                await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });
                
                // either on queue, passed queue or proxy timeout
                const queueStatus = await this.handleQueuePass();
                if(queueStatus !== 'PASSED'){
                    return queueStatus;
                }
                // NOW WE ARE PASSEDDD
                
                // Continue with login flow (skip the initial navigation)
                if (!this.currentUser) {
                    throw new Error('Current user not initialized');
                }

                this.log('Accepting cookie banner...');
                // now we are on the accoutn apge, first accept the cookie banner
                const cookieBannerResult: boolean = await this.humanInteractions.robustClick(
                    '#onetrust-accept-btn-handler', 
                    'Cookie banner', 
                    this.page,
                    3,
                    30,
                    this.log.bind(this),
                    'stabilize',
                    false
                );
                if(!cookieBannerResult){
                    this.log('Failed to accept cookie banner, continuing...')
                }else{
                    this.cookieBannerAccepted = true;
                    this.log('Cookie banner accepted');
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }

                
                const hasAccount = Boolean(this.currentUser.HAS_ACCOUNT);
                
                // Execute login or register (we're already on auth page)
                if (hasAccount) {
                    await this.fifa_login(submitLock);
                } else {
                    this.log(`Registering user ${this.currentUser.EMAIL}`);
                    await this.fifa_register(submitLock, 'entry');
                }
                
                // Check completion
                if (!this.page) {
                    throw new Error('Page not initialized');
                }
                
                const completionResult = await this.fifa_completion('entry');
                return completionResult;
            }
            
            // Regular flow (non-queue-pass)
            this.log(`Navigating to: ${startUrl}`);
            await this.humanInteractions.browser_navigate(startUrl, this.log.bind(this));

            // Simulate human reading the page after load
            await this.simulatePageReading();
            

            if (!this.currentUser) {
                throw new Error('Current user not initialized');
            }
            // wait for domcontentloaded here
            await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });
            const hasAccount = Boolean(this.currentUser.HAS_ACCOUNT);

            // Navigate to auth page
            if (type === 'entry') {
                await this.fifa_navigate_auth('learn_more');
            } else {
                await this.fifa_navigate_auth(hasAccount ? 'sign_in_button' : 'register_button');
              
            }
            
            // wait for domcontentloaded here
            await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });
                
            // Execute login or register
            if (hasAccount) {
                await this.fifa_login(submitLock);
            } else {
                this.log(`Registering user ${this.currentUser.EMAIL}`);
                await this.fifa_register(submitLock, type === 'entry-fifa-com' ? 'entry' : type);
            }
            // Now login should be done, lets check the result
            if (!this.page) {
                throw new Error('Page not initialized');
            }
      

            // now if we have the entry-fifa-com flow we need to go to tickets page and click learn more before continuing
            if(type === 'entry-fifa-com'){
                // we first need to check if we are login blocked, if we get redirected to fifa.com we are not, otherwise we are
                // check for 30 seconds
                let isLoginBlocked = true;
                for(let i = 0; i < 30; i++){
                    const currentUrl: string = await this.page?.url() || '';
                    if(currentUrl === 'https://www.fifa.com/en'){
                        isLoginBlocked = false;
                        break;
                    }
                    await this.page?.waitForTimeout(1000);
                }
                if(isLoginBlocked){
                    return "LOGIN_BLOCKED";
                }


                await this.humanInteractions.browser_navigate('https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets', this.log.bind(this));
                const clickLearnMoreResult: boolean = await this.humanInteractions.robustClick(
                    'a[href*="fifa-fwc26-us.tickets.fifa.com"]', 
                    'Learn more button', 
                    null,
                    3,
                    60,
                    this.log.bind(this)
                ); 
                if (!clickLearnMoreResult) {
                    throw new Error('Failed to click Learn more button');
                }
                const pageDetectionSuccess = await this.humanInteractions.detectAndSwitchToNewPage(this.context, this.log.bind(this));
                if (!pageDetectionSuccess) {
                    this.log('Failed to detect login redirect after retries, restarting flow...', 'error');
                    throw "PROXY_TIMEOUT";
                }else{
                    this.log('Detected new page successfully, url:', this.humanInteractions.page?.url());
                }
                
                // Update the page reference after successful detection
                this.page = this.humanInteractions.page;
            }

            // wait for dom content
            await this.page?.waitForLoadState('domcontentloaded', { timeout: 35000 });
            

            const completionResult = await this.fifa_completion(type === 'entry-fifa-com' ? 'entry' : type);
            if(completionResult){
                return completionResult;
            }else{
                return "PROXY_TIMEOUT";
            }
        }catch(error: any){
            //console.log(error)
            return error.message;
        }
    }

}

export default FifaAutomation;
