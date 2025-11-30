// Types and interfaces
interface Colors {
    green: string;
    red: string;
    reset: string;
}

interface CsvFile {
    name: string;
    path: string;
    relativePath: string;
}

interface BulkResults {
    total: number;
    completed: number;
    failed: number;
    inProgress: number;
}

interface UserData {
    user: any;
    originalIndex: number;
    taskNumber: number;
}

/**
 * Queue-based submit lock to prevent race conditions
 * Ensures only one thread can submit at a time with FIFO ordering
 * 
 * How it works:
 * 1. acquire() returns a Promise that resolves with a release function
 * 2. If unlocked: immediately grants access and marks as locked
 * 3. If locked: queues the resolve callback to be called when lock is released
 * 4. release() processes next queued thread or unlocks if queue is empty
 */
class SubmitLock {
    private queue: Array<(release: () => void) => void> = [];
    private locked = false;

    async acquire(): Promise<() => void> {
        return new Promise((resolve) => {
            if (!this.locked) {
                // Lock is free - acquire immediately
                this.locked = true;
                resolve(() => this.release());
            } else {
                // Lock is busy - add to queue
                // Store the resolve callback to be called when lock is released
                this.queue.push(resolve);
            }
        });
    }

    private release(): void {
        // Check if there's a waiting thread in the queue
        const nextResolve = this.queue.shift();
        
        if (nextResolve) {
            // Pass lock to next waiting thread
            // Lock stays true, we just pass the release function to next thread
            nextResolve(() => this.release());
        } else {
            // No one waiting - unlock
            this.locked = false;
        }
    }
}

/**
 * Global rate limit handler for Dolphin API 429 errors
 * When 429 is detected, pauses all threads for 3 minutes
 */
class RateLimitHandler {
    private static isPaused = false;
    private static pausePromise: Promise<void> | null = null;

    static async handle429Error(): Promise<void> {
        if (this.isPaused) {
            // Already paused, wait for existing pause to complete
            if (this.pausePromise) {
                await this.pausePromise;
            }
            return;
        }

        this.isPaused = true;
        console.log(`\n🚨 Dolphin API rate limit (429) detected - pausing all threads for 3 minutes...`);
        
        this.pausePromise = new Promise((resolve) => {
            setTimeout(() => {
                this.isPaused = false;
                this.pausePromise = null;
                console.log(`✅ Rate limit pause complete - resuming all threads`);
                resolve();
            }, 180000); // 3 minutes = 180,000ms
        });

        await this.pausePromise;
    }

    static async checkAndWait(): Promise<void> {
        if (this.isPaused && this.pausePromise) {
            await this.pausePromise;
        }
    }
}

// const puppeteer = require('puppeteer-core');
import * as readline from 'readline';
import DolphinAntyHelper from './helpers/dolphinAntyHelper';
import FifaAutomation from './modules/enterFifa';
import CsvHelper from './helpers/csvHelper';
import SettingsHelper from './helpers/settingsHelper';
import config from './helpers/config';
import ImapHelper from './helpers/imapHelper';
import * as fs from 'fs';
import * as path from 'path';
import { sendFinishedWebhook, sendQueuePassExpiredWebhook } from './helpers/discordWebhook';

// Ensure fetch is available (Node 18+ should have it globally)
if (typeof fetch === 'undefined') {
    console.log('Fetch not available, importing node-fetch...');
    global.fetch = require('node-fetch');
}

// ANSI color codes
const colors: Colors = {
    green: '\x1b[32m',
    red: '\x1b[31m',
    reset: '\x1b[0m'
};

// Cleanup function for graceful shutdown
async function cleanup(): Promise<void> {
    console.log('\nShutting down gracefully...');
    const imapHelper = ImapHelper.getInstance();
    await imapHelper.disconnect();
    console.log('Cleanup complete');
    process.exit(0);
}

// Register cleanup handlers
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);


// Initialize settings helper
const settings = new SettingsHelper();

const isDebug: boolean = settings.isDebugMode();
const API_TOKEN: string = settings.get('DOLPHYN_API_TOKEN') as string;
const API_BASE_URL: string = config.LOCAL_API_BASE_URL;

// Create readline interface for user input
const rl: readline.Interface = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// Initialize Dolphin Anty helper
const dolphinHelper = new DolphinAntyHelper();

// Function to ask for profile ID
function askForProfileId(): Promise<string> {
    return new Promise((resolve) => {
        rl.question('Enter your Dolphin Anty Profile ID: ', (profileId: string) => {
            resolve(profileId.trim());
        });
    });
}

function askForQueuePassCookie(): Promise<string | null> {
    return new Promise((resolve) => {
        rl.question('Enter the AcpAT-v3-10-FWC26-LotteryFCFS cookie value (or press Enter to skip): ', (cookie: string) => {
            const trimmed = cookie.trim();
            if (trimmed === '') {
                resolve(null);
            } else {
                resolve(trimmed);
            }
        });
    });
}

async function getCookieFromAPI(): Promise<string | null> {
    // get this api http://152.53.86.201:8000/cookie/fifa
    try{
        const response = await fetch(`http://152.53.86.201:8000/cookie/fifa`);
        if(!response.ok){
            return null;
        }
        const responseData = await response.json();
        return responseData.cookie;
    }catch(error: any){
        console.log('error, api might be down')
        return null;
    }
}



// Function to ask if user wants auto-restart
function askForAutoRestart(): Promise<{ enabled: boolean; times: number }> {
    return new Promise((resolve) => {
        rl.question('Enable auto-restart after completion? (y/N): ', (answer: string) => {
            const enabled = answer.toLowerCase().trim() === 'y' || answer.toLowerCase().trim() === 'yes';
            
            if (!enabled) {
                resolve({ enabled: false, times: 0 });
                return;
            }
            
            rl.question('How many times to restart? (1-5): ', (timesAnswer: string) => {
                const times = parseInt(timesAnswer.trim());
                
                if (isNaN(times) || times < 1 || times > 5) {
                    console.log('Invalid number. Using default: 1 restart');
                    resolve({ enabled: true, times: 1 });
                } else {
                    console.log(`Auto-restart enabled: ${times} time(s)`);
                    resolve({ enabled: true, times });
                }
            });
        });
    });
}

// Function to list and select CSV files
async function selectCsvFile(): Promise<string | null> {
    
    // Find all CSV files in the project directory
    const csvFiles: CsvFile[] = [];
    
    // Determine the correct directory to search for CSV files
    let projectDir: string;
    if ((process as any).pkg) {
        // For packaged executables, use the directory where the exe is located
        projectDir = path.dirname(process.execPath);
    } else {
        // For development, use current working directory
        projectDir = process.cwd();
    }
    
    // Function to recursively find CSV files
    function findCsvFiles(dir: string, relativePath: string = ''): void {
        try {
            const items: string[] = fs.readdirSync(dir);
            for (const item of items) {
                const fullPath: string = path.join(dir, item);
                const relativeItemPath: string = path.join(relativePath, item);
                    
                if (item.endsWith('.csv')) {
                    csvFiles.push({
                        name: item,
                        path: fullPath,
                        relativePath: relativeItemPath
                    });
                }
            }
        } catch (error: any) {
            console.log(`Error reading directory ${dir}: ${error.message}`);
        }
    }
    
    findCsvFiles(projectDir);
    
    if (csvFiles.length === 0) {
        console.log(' No CSV files found in the project directory.');
        return null;
    }
    
    // Clear the console for better UX
    console.clear();
    console.log('Tasks:');
    
    
    csvFiles.forEach((file: CsvFile, index: number) => {
        const number: number = index + 1;
        console.log(`${number}. ${file.name}`);
    });
    
    // Get user selection
    return new Promise((resolve) => {
        rl.question(`Select a task to start: (1-${csvFiles.length}) `, (answer: string) => {
            const selection: string = answer.trim().toLowerCase();
            
            if (selection === 'q' || selection === 'quit') {
                console.log('CSV selection cancelled.');
                resolve(null);
                return;
            }
            
            const fileIndex: number = parseInt(selection) - 1;
            
            if (isNaN(fileIndex) || fileIndex < 0 || fileIndex >= csvFiles.length) {
                console.log('Invalid selection. Please try again.');
                resolve(selectCsvFile()); // Recursive call to try again
                return;
            }
            
            const selectedFile: CsvFile = csvFiles[fileIndex];
            console.log(`Selected: ${selectedFile.name}`);
            
            resolve(selectedFile.path);
        });
    });
}

// Function to ask for action
function askForAction(): Promise<string> {
    return new Promise((resolve) => {
        console.log('\nAvailable actions:');
        
        if (isDebug) {
            // Dev mode - show all options
            console.log('1. Use existing profile');
            console.log('2. Create new profile');
            console.log('3. Create multiple profiles');
            console.log('4. View proxy statistics');
            console.log('5. Clean up all profiles');
            console.log('6. Test FIFA automation');
            console.log('7. Test FIFA automation with specific user');
            console.log('8. View CSV data');
            console.log('9. Create profile & test FIFA automation');
            console.log('10. Test IMAP email checking');
            console.log('11. Test credit card form only');
            console.log('12. BULK FIFA ENTRY PROCESSING (Create New Profiles)');
            console.log('13. BULK FIFA ENTRY PROCESSING (Use Existing Profiles)');
            console.log('14. Exit');
            
            rl.question('Select an action (1-14): ', (action: string) => {
                resolve(action.trim());
            });
        } else {
            // Production mode - only show main option
            console.log('1. Start FIFA Entry');
            console.log('2. Start FIFA Entry with FIFA.com page flow');
            console.log('3. Generate accounts');
            console.log('4. Fifa BEAST MODE');
            // console.log('5. Run queue passes');
            console.log('6. Exit');
            
            rl.question('Select an action (1-5): ', (action: string) => {
                resolve(action.trim());
            });
        }
    });
}

// Function to authenticate with Dolphin Anty
async function authenticate(): Promise<boolean> {
    try {
        // Add timeout to prevent hanging
        const controller: AbortController = new AbortController();
        const timeoutId: NodeJS.Timeout = setTimeout(() => controller.abort(), 10000); // 10 second timeout
        
        const response: Response = await fetch(`${API_BASE_URL}/auth/login-with-token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: API_TOKEN
            }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        
        const result: any = await response.json();
       
        if (result.success) {
            console.log(`${colors.green}Connected to doplhin${colors.reset}`);
            return true;
        } else {
            return false;
        }
    } catch (error) {
        return false;
    }
}

// Profile management functions moved to FIFA module


/**
 * Bulk FIFA Entry Processing with auto-restart support
 */
async function startBulkFifaProcessing(
    csvFilePath: string | null = null, 
    type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry',
    autoRestart: { enabled: boolean; times: number } = { enabled: false, times: 0 },
    currentRun: number = 1,
    queuePassCookie: string | null = null,
    useAPIforQueuePass: boolean = false
): Promise<void> {
    try {
        
        // ALWAYS reload CSV data fresh (especially important for restarts)
        console.log(`\n${'='.repeat(60)}`);
        if (autoRestart.enabled && currentRun > 1) {
            console.log(`AUTO-RESTART ${currentRun - 1}/${autoRestart.times} - Reloading CSV data...`);
        } else if (autoRestart.enabled) {
            console.log(`INITIAL RUN (Auto-restart: ${autoRestart.times}x) - Loading CSV data...`);
        } else {
            console.log('Loading CSV data...');
        }
        console.log(`${'='.repeat(60)}\n`);
        
        const csvHelper = CsvHelper.getInstance(csvFilePath);
        await csvHelper.readCsvData(true); // Force reload to get fresh data
        
        const availableUsers: any[] = csvHelper.getAvailableUsers(type); 

        console.log(`Pending completion tasks: ${availableUsers.length}`);
        
        if (availableUsers.length === 0) {
            console.log('All tasks have already been processed!');
            
            // Check if we should restart
            if (autoRestart.enabled && currentRun <= autoRestart.times) {
                console.log(`\n${'='.repeat(60)}`);
                console.log(`All tasks completed, but ${availableUsers.length} tasks available`);
                console.log(`Restart ${currentRun}/${autoRestart.times} - No pending tasks to process`);
                console.log(`${'='.repeat(60)}\n`);
            }
            
            console.log('Check your CSV file if you want to reset some entries.');
            return;
        }
        
        // Get thread count from settings
        const threadCount: number = settings.getThreadNum();
        console.log(`${threadCount} threads loaded`);

        // read proxies from proxies.txt
        let proxies: string[];
        try {
            let proxyData: string = fs.readFileSync((settings as any).proxyPath, 'utf8');
            proxies = proxyData.split('\n').filter(p => p.trim()); // Filter empty lines
            if(proxies.length === 0) {
                console.log('No proxies found in proxies.txt');
                return;
            }
            console.log(`${proxies.length} proxies loaded`);
            if (proxies.length < availableUsers.length){
                console.log(`${colors.red}Warning: you have less proxies than users. Some proxies will be reused${colors.reset}`);
            }
        } catch (error: any) {
            if(error.message.includes('ENOENT')) {
                console.log(`${colors.red}proxies.txt file not found, creating it...${colors.reset}`);
                settings.createBlankProxies();
                console.log('Please add proxies to proxies.txt and run the script again');
                process.exit(1);    
            }
            return;
        }
        
        // Only ask for confirmation on the first run
        if (currentRun === 1) {
            const confirmation: boolean = await new Promise((resolve) => {
                rl.question('Start bulk processing? (y/N): ', (answer: string) => {
                    resolve(answer.toLowerCase().trim() === 'y' || answer.toLowerCase().trim() === 'yes');
                });
            });
            
            if (!confirmation) {
                console.clear();
                return;
            }
        }
        
        // Create user queue with sequential task numbers
        const userQueue: UserData[] = availableUsers.map((user: any, index: number) => {
            const originalIndex: number = csvHelper.getAllUsers().findIndex((u: any) => u.EMAIL === user.EMAIL) as number;
            return { user, originalIndex, taskNumber: index + 1 };
        });
        
        // Start the bulk processor
        await runBulkProcessor(threadCount, userQueue, proxies, type, csvFilePath, queuePassCookie, useAPIforQueuePass);
        
        // Check if we should auto-restart
        if (autoRestart.enabled && currentRun < autoRestart.times) {
            console.log(`\n${'='.repeat(60)}`);
            console.log(`PREPARING AUTO-RESTART ${currentRun}/${autoRestart.times}`);
            console.log(`Waiting 5 seconds before restarting...`);
            console.log(`${'='.repeat(60)}\n`);
            
            await new Promise(resolve => setTimeout(resolve, 5000));
            
            // Recursive call for next restart with fresh CSV data
            await startBulkFifaProcessing(csvFilePath, type, autoRestart, currentRun + 1, queuePassCookie);
        } else if (autoRestart.enabled && currentRun === autoRestart.times) {
            console.log(`\n${'='.repeat(60)}`);
            console.log(`AUTO-RESTART COMPLETE - All ${autoRestart.times} runs finished!`);
            console.log(`${'='.repeat(60)}\n`);
        }
        
    } catch (error: any) {
        console.error(' Error in bulk processing setup:', error.message);
    }
}

/**
 * Run bulk FIFA processing with multiple threads
 */
async function runBulkProcessor(
    threadCount: number, 
    userQueue: UserData[], 
    proxies: string[], 
    type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry', 
    csvFilePath: string | null = null,
    queuePassCookie: string | null = null,
    useAPIforQueuePass: boolean = false
): Promise<void> {
    console.log(`\nStarting ${threadCount} worker threads...`);
    
    // Create a single shared submit lock for all threads
    const submitLock = new SubmitLock();
    console.log('Submit lock created - all threads will use the same queue\n');
    
    // userQueue is already created with user and originalIndex
    const workers: Promise<void>[] = [];
    const results: BulkResults = {
        total: userQueue.length,
        completed: 0,
        failed: 0,
        inProgress: 0
    };
    
    let isShuttingDown: boolean = false;
    const startTime: number = Date.now();
    
    // Progress update function
    const showProgress = (): void => {        
        const remaining = userQueue.length + 1;
        const processed = results.completed + results.failed;
        
        // Update terminal title using ANSI escape sequences (works on macOS, Windows, Linux)
        const title = `Fifabot | Remaining: ${remaining} | Completed: ${results.completed} | Failed: ${results.failed}`;
        
        // Set terminal title using escape sequences
        process.stdout.write(`\x1b]0;${title}\x07`);
        
        // Also try to set process.title (works on Windows and some systems)
        process.title = title;
    };
    
    // Show progress every 5 seconds
    const progressInterval: NodeJS.Timeout = setInterval(showProgress, 5000);
    
    // Handle graceful shutdown
    process.on('SIGINT', () => {
        console.log('\n\nShutdown signal received...');
        console.log('Waiting for current tasks to complete...');
        isShuttingDown = true;
        clearInterval(progressInterval);
        
        // Stop all workers gracefully
        workers.forEach(worker => {
            if (worker && (worker as any).stop) {
                (worker as any).stop();
            }
        });
    });
    
    // Create worker function - simplified version
    async function createWorker(
        workerId: number, 
        imapHelper: any, 
        submitLock: SubmitLock, 
        type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry',
        retryCount: number = 0
    ): Promise<void> { 
        while (!isShuttingDown && userQueue.length > 0) {
            const userData: UserData | undefined = userQueue.shift();
            if (!userData) break;
            
            // Wait if rate limited (429 error)
            await RateLimitHandler.checkAndWait();
            
            // Validate userData structure
            if (!userData.user || typeof userData.originalIndex !== 'number' || typeof userData.taskNumber !== 'number') {
                console.error(`Worker ${workerId}: Invalid userData structure:`, userData);
                results.failed++;
                continue;
            }
            
            const { user, originalIndex, taskNumber } = userData;
            results.inProgress++;
            
            
            let fifaBot: FifaAutomation | null = null;
            let isInQueue = false; // Track if task is in queue
            const taskStartTime = Date.now();
            const MAX_RUNTIME = 15 * 60 * 1000; // 15 minutes in milliseconds
            
            try {
                // Create FIFA bot instance
                fifaBot = new FifaAutomation();
                
                // Run complete FIFA process (includes profile creation, automation, and cleanup)
                // Pass the proxies loaded from proxies.txt
                let startUrl: string = 'https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets';
                if(type === 'entry-fifa-com' || type === 'account'){
                    startUrl = 'https://www.fifa.com/en';
                } else if(type === 'entry-queuepass'){
                    startUrl = 'https://fifa-fwc26-us.tickets.fifa.com/';
                }

                
                // For queue-pass runs, fetch a fresh cookie per task
                let taskQueuePassCookie: string | null = null;
                if(useAPIforQueuePass){
                    taskQueuePassCookie = queuePassCookie;
                    if (type === 'entry-queuepass') {
                        try {
                            taskQueuePassCookie = await getCookieFromAPI();
                        } catch {}
                    }
                }else{
                    taskQueuePassCookie = queuePassCookie;
                }

                // For beast mode (entry-queuepass), race against timeout
                // For other modes, just run the task
                let result: any;
                
                if (type === 'entry-queuepass') {
                    // Create a timeout promise (15 minutes unless in queue)
                    const timeoutPromise = new Promise<string>((_, reject) => {
                        const checkInterval = setInterval(() => {
                            const elapsed = Date.now() - taskStartTime;
                            
                            // Check if bot is in queue (you'll need to expose this in FifaAutomation)
                            // For now, we'll just check runtime
                            if (!isInQueue && elapsed >= MAX_RUNTIME) {
                                clearInterval(checkInterval);
                                reject(new Error('TASK_TIMEOUT'));
                            }
                        }, 5000); // Check every 5 seconds
                    });

                    // Race between task completion and timeout (only for beast mode)
                    result = await Promise.race([
                        fifaBot.initFifaFlow(
                            user, 
                            taskNumber, 
                            proxies, 
                            imapHelper, 
                            startUrl, 
                            type,
                            userQueue.length,
                            submitLock,  // Pass the shared submit lock
                            taskQueuePassCookie  // Pass a fresh queue pass cookie per task
                        ),
                        timeoutPromise
                    ]).catch(err => {
                        if (err.message === 'TASK_TIMEOUT') {
                            return 'TASK_TIMEOUT';
                        }
                        throw err;
                    });
                } else {
                    // For non-beast modes, just run the task without timeout
                    result = await fifaBot.initFifaFlow(
                        user, 
                        taskNumber, 
                        proxies, 
                        imapHelper, 
                        startUrl, 
                        type,
                        userQueue.length,
                        submitLock,  // Pass the shared submit lock
                        taskQueuePassCookie  // Pass a fresh queue pass cookie per task
                    );
                }
                
                switch(result){
                    case 'TASK_TIMEOUT':
                        console.log(` Worker ${workerId}: Task ${taskNumber} exceeded 15 minute limit - ${user.EMAIL}`);
                        results.failed++;
                        break;
                    case 'DOLPHIN_RATE_LIMIT_429':
                        console.log(` Worker ${workerId}: Dolphin API rate limit detected - pausing all threads`);
                        await RateLimitHandler.handle429Error();
                        // Requeue the user to try again after pause
                        userQueue.unshift({ user, originalIndex, taskNumber });
                        break;
                    case 'NO_PROXIES_AVAILABLE':
                        console.log(` Worker ${workerId}: No unused proxies available - stopping bulk processing`);
                        isShuttingDown = true;
                        break;
                    case 'QUEUE_PASS_EXPIRED':
                        console.log(` Worker ${workerId}: Queue pass expired for ${user.EMAIL} (Task ${taskNumber})`);
                        results.failed++;
                        isShuttingDown = true; // Stop processing if queue pass expired
                        break;
                    case 'DATA_DOME_BLOCKED':
                        if(settings.get('DD_BLOCK_RETRY')){
                            const ddBlockRetry: number = parseInt(settings.get('DD_BLOCK_RETRY') as string);
                            // remove the exact proxy used by this task from the in-memory list
                            try {
                                const usedProxy = fifaBot?.getActiveProxyString?.();
                                if (usedProxy) {
                                    const idx = proxies.indexOf(usedProxy);
                                    if (idx !== -1) {
                                        proxies.splice(idx, 1);
                                        //console.log(`Removed blocked proxy from list: ${usedProxy}`);
                                    }
                                }
                            } catch {}

                            // Retry same user with a different proxy if within retry budget
                            if (ddBlockRetry >= retryCount) {
                                // Requeue the same user at the front so the next loop picks it again
                                userQueue.unshift({ user, originalIndex, taskNumber });
                                // Restart the worker with incremented retry counter
                                return createWorker(workerId, imapHelper, submitLock, type, retryCount + 1);
                            } else {
                                results.failed++;
                                console.log(`Worker ${workerId}: Failed to process ${user.EMAIL} (Task ${taskNumber}):`, result);
                                break;
                            }
                        }
                        break;
                    case true:
                        results.completed++;
                        //console.log(`Worker ${workerId}: Successfully completed ${user.EMAIL} (Task ${taskNumber})`);
                        break;
                    case 'ENTERED_DRAW':
                        results.completed++;
                        //console.log(`Worker ${workerId}: Successfully completed ${user.EMAIL} (Task ${taskNumber})`);
                        break;

                    default:
                        results.failed++;
                        console.log(`Worker ${workerId}: Failed to process ${user.EMAIL} (Task ${taskNumber}):`, result);
                        break;
                }
               
                
            } catch (error: any) {
                console.error(` Worker ${workerId}: Failed to process ${user.EMAIL} (Task ${taskNumber}):`, error.message);
                results.failed++;
                
                
            } finally {
                // ALWAYS ensure cleanup happens
                if (fifaBot) {
                    try {
                        await fifaBot.close();
                    } catch (cleanupError: any) {
                        console.error(`Worker ${workerId}: Error during cleanup:`, cleanupError.message);
                    }
                }
                
                results.inProgress--;
                //console.log(`Worker ${workerId}: Task ${taskNumber} completed. ${userQueue.length} users remaining.`);
            }
        }
        
        //console.log(`Worker ${workerId}: Finished processing`);
    }

    // Start all workers
    for (let i = 1; i <= threadCount; i++) {
        const workerImapHelper = new ImapHelper(); // Create separate instance per worker
        const worker = createWorker(i, workerImapHelper, submitLock, type, 0);
        workers.push(worker);
        
        if (i < threadCount) {
            console.log(`Worker ${i} started, waiting 7 seconds before starting worker ${i + 1}...`);
            await new Promise(resolve => setTimeout(resolve, 7000));
        }
        
    }
    
    // Wait for all workers to complete
    await Promise.all(workers);
    
    // Clean up
    clearInterval(progressInterval);
    
    // Final results
    const totalTime: number = Math.round((Date.now() - startTime) / 1000);
    const totalProcessed: number = results.completed + results.failed;
    
    console.log(`Total time: ${Math.floor(totalTime / 60)}m ${totalTime % 60}s`);
    console.log(`Final Results:`);
    console.log(`   Successful: ${results.completed}`);
    console.log(`   Failed: ${results.failed}`);
    console.log(`   Total processed: ${totalProcessed}`);
    console.log(`   Success rate: ${totalProcessed > 0 ? Math.round((results.completed / totalProcessed) * 100) : 0}%`);
    console.log(`   Avg time per user: ${totalProcessed > 0 ? Math.round(totalTime / totalProcessed) : 0}s`);

    // now if FINISHED_WEBHOOK has a value, send discord webhook to here
    const finishedWebhook: string = settings.get('FINISHED_WEBHOOK') as string;
    if (csvFilePath && finishedWebhook) {
        await sendFinishedWebhook(path.basename(csvFilePath as string));
    }
    if (results.completed > 0) {
        console.log('Congratulations! FIFA entries have been submitted!');
    }
    if (isShuttingDown) {
        if (userQueue.length > 0) {
            console.log(`Processing was interrupted. ${userQueue.length} users remain in queue.`);
        } else {
            console.log(`Processing stopped due to no unused proxies available.`);
        }
    }
    if (results.failed > 0) {
        console.log('Failed entries can be retried by running bulk processing again.');
    }
}

async function testEntryFlow(): Promise<void> {
    try {
        const fifaBot = new FifaAutomation();
        const workerImapHelper = new ImapHelper();
        await fifaBot.testEntryFlow(workerImapHelper);

        const finishedWebhook: string = settings.get('FINISHED_WEBHOOK') as string;
        const csvFilePath: string = 'test entry flow';
        if (csvFilePath && finishedWebhook) {
            await sendFinishedWebhook(csvFilePath);
        }
    } catch (error: any) {
        console.error(' Error in test address filling:', error.message);
    }
}

async function askForThreadCount(): Promise<number> {
    return new Promise((resolve) => {
        rl.question('Enter the number of threads to use: ', (threads: string) => {
            resolve(parseInt(threads.trim()));
        });
    });
}


async function queueLoopFlow(threads: number): Promise<void> {
    try{
      for(let i = 1; i <= threads; i++){
        const workerImapHelper = new ImapHelper();
        // directly run initFifaFlow with the queue pass cookie
      }
    }catch(error: any){
        console.error(' Error in queue loop flow:', error.message);
    }
}


// Main function
async function main(firstTime: boolean = false): Promise<void> {
    try {
        // Authenticate
        const authSuccess: boolean = await authenticate();
        if (!authSuccess) {
            if(!firstTime) console.log(`${colors.red}Error connecting to doplhin, waiting for doplhin to be started...${colors.reset}`);
            await new Promise(resolve => setTimeout(resolve, 3000));
            return main(true);
        }

        while (true) {
            const action: string = await askForAction();
            let selectedCsvPath: string | null = null;
            let autoRestartConfig: { enabled: boolean; times: number } = { enabled: false, times: 0 };
            let queuePassCookie: string | null = null;
        
            switch (action) {
                case '1': // Start FIFA Entry Processing
                    // First, let user select CSV file
                    selectedCsvPath = await selectCsvFile();
                    if (selectedCsvPath) {
                        // Ask for auto-restart
                        autoRestartConfig = await askForAutoRestart();
                        console.clear();
                        await startBulkFifaProcessing(selectedCsvPath, 'entry', autoRestartConfig);
                    }
                    break;
                case '2': // entry with fifa.com page flow
                    // First, let user select CSV file
                    selectedCsvPath = await selectCsvFile();
                    if (selectedCsvPath) {
                        // Ask for auto-restart
                        autoRestartConfig = await askForAutoRestart();
                        console.clear();
                        await startBulkFifaProcessing(selectedCsvPath, 'entry-fifa-com', autoRestartConfig);
                    }
                    break;
                case '3': // Generate accounts
                   // First, let user select CSV file
                   selectedCsvPath = await selectCsvFile();
                   if (selectedCsvPath) {
                       // Ask for auto-restart
                       autoRestartConfig = await askForAutoRestart();
                       console.clear();
                       await startBulkFifaProcessing(selectedCsvPath, 'account', autoRestartConfig);
                   }
                   break;
                case '4': // Start FIFA Entry with Queue Pass
                   // check if api is up
                   let useAPIforQueuePass = true;
                   let queuePassCookie = await getCookieFromAPI();
                   if(!queuePassCookie){
                     console.log('No queue pass cookie found, set it yourself..');
                     useAPIforQueuePass = false;
                     queuePassCookie = await askForQueuePassCookie();
                   }
                  
                   if (queuePassCookie) {
                       selectedCsvPath = await selectCsvFile();
                       if (selectedCsvPath) {
                           autoRestartConfig = await askForAutoRestart();
                           console.clear();
                           await startBulkFifaProcessing(selectedCsvPath, 'entry-queuepass', autoRestartConfig, 1, queuePassCookie, useAPIforQueuePass);
                       }
                   }
                   break;
                case '5': // Start FIFA Entry with Queue Pass using API
                    let threadCount = await askForThreadCount();
              
                case '6': // Exit
                    console.log('Goodbye!');
                    rl.close();
                    process.exit(0);
                case '7': // test address filling
                    await testEntryFlow();
                    break;
                
                default:
                    console.log('Invalid action. Please select 1-6.');
                    break;
            }
            
        }

    } catch (error: any) {
        console.error(' Unexpected error:', error);
        process.exit(1);
    }
}

// Handle unhandled errors to prevent crashes
process.on('unhandledRejection', (reason: any, promise: Promise<any>) => {
    console.error('Unhandled Rejection at:', promise, 'reason:', reason);
    // Don't exit the process, just log the error
});

process.on('uncaughtException', (error: Error) => {
    console.error('Uncaught Exception:', error);
    // Don't exit the process, just log the error
});

// Start the script
main();
