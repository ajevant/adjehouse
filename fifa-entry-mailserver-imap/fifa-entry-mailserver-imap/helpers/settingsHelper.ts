import * as fs from 'fs';
import * as path from 'path';

// ANSI color codes
const colors = {
    green: '\x1b[32m',
    reset: '\x1b[0m'
};

/**
 * Helper class to read and manage settings from settings.txt
 * Implements singleton pattern to avoid multiple initialization
 */
class SettingsHelper {
    private static instance: SettingsHelper | null = null;
    private execDir: string = '';
    private settingsPath: string;
    private proxyPath: string;
    private settings: Record<string, any>;
    
    static getInstance(): SettingsHelper {
        if (!SettingsHelper.instance) {
            SettingsHelper.instance = new SettingsHelper();
        }
        return SettingsHelper.instance;
    }

    constructor(settingsPath: string | null = null) {
        // If no path provided, look for settings.txt in the same directory as the executable
        if (!settingsPath) {
            let execDir: string;
            
            if ((process as any).pkg) {
                // For packaged executables, ALWAYS use the directory where the exe is located
                execDir = path.dirname(process.execPath);
            } else {
                // For development, use current working directory
                execDir = process.cwd();
            }
            this.execDir = execDir;
            this.settingsPath = path.join(execDir, 'settings.txt');
            this.proxyPath = path.join(execDir, 'proxies.txt');
        
        } else {
            this.settingsPath = settingsPath;
            this.proxyPath = path.join(path.dirname(settingsPath), 'proxies.txt');
        }
        
        this.settings = {};
        this.loadSettings();
    }

    /**
     * Load settings from the settings.txt file
     */
    async loadSettings(): Promise<void> {
        try {
            const settingsFile = path.resolve(this.settingsPath);
            
            if (!fs.existsSync(settingsFile)) {
                console.error('settings.txt file not found, creating it...');
                this.createBlankSettings();

                const proxyFile = path.resolve(this.proxyPath);
                if (!fs.existsSync(proxyFile)) {
                    console.error(`proxies.txt file not found, creating it...`);
                    this.createBlankProxies();
                }

                return process.exit(1);
            }

            const content = fs.readFileSync(settingsFile, 'utf-8');
            const lines = content.split('\n').filter(line => line.trim() && !line.startsWith('#'));

            for (const line of lines) {
                const [key, ...valueParts] = line.split('=');
                const value = valueParts.join('=').trim(); // Handle values with = in them
                
                if (key && value) {
                    this.settings[key.trim()] = value;
                }
            }

            await this.validateSettings();
            
        } catch (error: any) {
            console.error('Error loading settings:', error.message);
            return process.exit(1);
        }
    }

    createBlankProxies(): void {
        const proxiesTemplate = `ip:port:auth:password`;
        fs.writeFileSync(path.join(this.execDir, 'proxies.txt'), proxiesTemplate);
        console.log('Created proxies.txt template');
    }

    async createBlankSettings(): Promise<void> {
        const settingsTemplate = 
        `THREAD_NUM=3
IMAP_SERVER=imap.gmail.com
EMAIL=your-email@gmail.com
IMAP_PASSWORD=your-app-password
DOLPHYN_API_TOKEN=your-dolphin-api-token
DISCORD_WEBHOOK=your-discord-webhook-url
DEBUG=FALSE
FLAG_OTP_ISSUES=FALSE
PLATFORM=windows
FINISHED_WEBHOOK=
CAPSOLVER_KEY=
DD_BLOCK_RETRY=
`;
    
        fs.writeFileSync(path.join(this.execDir, 'settings.txt'), settingsTemplate);
        console.log('Created settings.txt template');
       
    }

    /**
     * Validate that all required settings are present
     */
    async validateSettings(): Promise<void> {
        const requiredSettings = ['THREAD_NUM', 'IMAP_SERVER', 'EMAIL', 'IMAP_PASSWORD', 'DOLPHYN_API_TOKEN', 'DISCORD_WEBHOOK', 'DEBUG', 'PLATFORM', 'CAPSOLVER_KEY'];
        const missingSettings: string[] = [];

        for (const setting of requiredSettings) {
            if (!this.settings[setting] || 
                this.settings[setting] === 'your-email@gmail.com' || 
                this.settings[setting] === 'your-app-password' ||
                this.settings[setting] === 'your-dolphin-api-token' ||
                this.settings[setting] === 'your-discord-webhook-url') {
                missingSettings.push(setting);
            }
        }

        if (missingSettings.length > 0) {
            console.error('Missing or invalid settings in settings.txt:');
            missingSettings.forEach(setting => console.error(`   - ${setting}`));
            console.log('Please update settings.txt with valid values');
            console.log('\nPress Ctrl+C to close the application when you are done reading the logs.');
            // Keep process alive so user can see the logs
            await SettingsHelper.keepProcessAlive();
        }

        // Validate thread number
        const threadNum = parseInt(this.settings.THREAD_NUM);
        if (isNaN(threadNum) || threadNum < 1 ) {
            console.error('THREAD_NUM must be at least 1');
            console.log('\nPress Ctrl+C to close the application when you are done reading the logs.');
            await SettingsHelper.keepProcessAlive();
        }

        // Validate debug setting
        const debugValue = this.settings.DEBUG.toUpperCase();
        if (debugValue !== 'TRUE' && debugValue !== 'FALSE') {
            console.error('DEBUG must be either TRUE or FALSE');
            console.log('\nPress Ctrl+C to close the application when you are done reading the logs.');
            await SettingsHelper.keepProcessAlive();
        }

        // Validate platform setting (required)
        const platform = this.settings.PLATFORM.toLowerCase();
        if (platform !== 'windows' && platform !== 'macos') {
            console.error(`Invalid PLATFORM value: ${this.settings.PLATFORM}`);
            console.error(`PLATFORM must be either 'windows' or 'macos'`);
            console.log('\nPress Ctrl+C to close the application when you are done reading the logs.');
            await SettingsHelper.keepProcessAlive();
        }

        console.log(`${colors.green}All settings validated${colors.reset}`);
    }

    /**
     * Keep the process alive so user can see error logs
     * Process will only exit when user presses Ctrl+C
     */
     static async keepProcessAlive(): Promise<void> {
       // keep open for 30seconds
       await new Promise(resolve => setTimeout(resolve, 30000));
       process.exit(1);
    }

    /**
     * Get a setting value
     * @param {string} key - Setting key
     * @returns {string|null} Setting value or null if not found
     */
    get(key: string): string | null {
        return this.settings[key] || null;
    }

    /**
     * Get thread number as integer
     * @returns {number} Number of threads
     */
    getThreadNum(): number {
        return parseInt(this.settings.THREAD_NUM);
    }

    /**
     * Get platform (windows or macos)
     * @returns {string} Platform value in lowercase
     */
    getPlatform(): string {
        return this.settings.PLATFORM.toLowerCase();
    }

    /**
     * Get IMAP configuration object
     * @returns {Object} IMAP configuration
     */
    getImapConfig(): any {
        return {
            server: this.settings.IMAP_SERVER,
            email: this.settings.EMAIL,
            password: this.settings.IMAP_PASSWORD
        };
    }

    /**
     * Check if debug mode is enabled
     * @returns {boolean} True if debug mode is enabled
     */
    isDebugMode(): boolean {
        return this.settings.DEBUG.toUpperCase() === 'TRUE';
    }

    /**
     * Check if OTP issues should be flagged
     * @returns {boolean} True if OTP issues should be flagged
     */
    shouldFlagOtpIssues(): boolean {
        return this.settings.FLAG_OTP_ISSUES?.toUpperCase() === 'TRUE';
    }

    /**
     * Display current settings (hide sensitive data)
     */
    displaySettings(): void {
        console.log('Current Settings:');
        console.log(`Threads: ${this.settings.THREAD_NUM}`);
        console.log(`Email: ${this.settings.EMAIL}`);
        console.log(`Discord Webhook: ${this.settings.DISCORD_WEBHOOK}`);
    }
}

export default SettingsHelper;