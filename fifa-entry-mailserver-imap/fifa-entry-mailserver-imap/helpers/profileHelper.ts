import config from './config';
import DolphinAntyHelper from './dolphinAntyHelper';
import ProxyHelper from './proxyHelper';
import UtilityHelper from './utilityHelper';
import SettingsHelper from './settingsHelper';

/**
 * Profile Helper - Functions for profile management
 * Contains functions for creating, starting, stopping, and deleting profiles
 */
class ProfileHelper {
    private dolphinHelper: DolphinAntyHelper;
    private lastAssignedProxyString: string | null = null;
    private profileId: string | null;
    private proxyId: string | null;
    private browserPath: string | null;
    private settings: SettingsHelper;

    constructor() {
        this.dolphinHelper = new DolphinAntyHelper();
        this.profileId = null;
        this.proxyId = null;
        this.browserPath = null;
        this.settings = SettingsHelper.getInstance();
    }

    /**
     * Start an existing profile by ID (for testing)
     * @param {string} profileId - Existing profile ID
     * @param {Function} logFunction - Logging function
     * @returns {Promise<{success: boolean, profileData?: any}>} Success status and profile data
     */
    async startExistingProfile(profileId: string, logFunction: Function): Promise<{success: boolean, profileData?: any}> {
        try {
            this.profileId = profileId;
            logFunction(`Starting existing profile: ${profileId}`);
            
            // Fetch profile information to get fingerprint
            const profileInfo = await this.dolphinHelper.getProfile(profileId);
            const profileData = profileInfo?.data || profileInfo;
            
            logFunction(`Fetched profile info: ${JSON.stringify(profileData).substring(0, 200)}`);
            
            const response = await fetch(`${config.LOCAL_API_BASE_URL}/browser_profiles/${profileId}/start?automation=1`, {
                method: 'GET'
            });

            const result = await response.json();
            
            if (result.success && result.automation) {
                this.browserPath = result.automation;
                logFunction(`Profile started successfully`);
                return { success: true, profileData: profileData };
            } else {
                logFunction(`Failed to start profile: ${JSON.stringify(result)}`, 'error');
                return { success: false };
            }
        } catch (error: any) {
            logFunction(`Error starting profile: ${error.message}`, 'error');
            return { success: false };
        }
    }

    /**
     * Create and start a new profile for this FIFA instance with proxy rotation
     * @param {Array} proxies - Array of proxy strings
     * @param {number} taskNumber - Task number (1-based)
     * @param {Function} logFunction - Logging function
     * @param {number} maxRetries - Maximum number of retries (default: 3)
     * @returns {Promise<boolean|string>} Success status or error code
     */
    async createAndStartProfile(proxies: string[], taskNumber: number, logFunction: Function, maxRetries: number = 3): Promise<any> {
        let lastError: any = null;
        let usedProxies: Set<string> = new Set(); // Track used proxies to avoid retrying dead ones
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                logFunction(`Creating new profile... (Attempt ${attempt}/${maxRetries})`);
                
                // Assign proxy for this task (will rotate to next proxy if previous failed)
                const proxyString: string | null = ProxyHelper.assignProxy(proxies, taskNumber + attempt - 1, logFunction);
                if (!proxyString) {
                    logFunction('No proxy available for this task', 'error');
                    return 'NO_PROXIES_AVAILABLE';
                }
                this.lastAssignedProxyString = proxyString;
                
                // Skip if we've already tried this proxy
                if (usedProxies.has(proxyString)) {
                    logFunction(`Skipping already used proxy: ${proxyString}`, 'warn');
                    continue;
                }
                usedProxies.add(proxyString);
                
                // Parse the assigned proxy
                const proxyData: any | null = ProxyHelper.parseProxy(proxyString, logFunction);
                if (!proxyData) {
                    logFunction('Invalid proxy format', 'error');
                    continue; // Try next proxy
                }
                
                logFunction(`Trying proxy: ${proxyData.host}:${proxyData.port}`);
                
                // Check if proxy already exists in Dolphin Anty (check full credentials)
                let dolphinProxy: any | null = await this.dolphinHelper.getProxyByCredentials(proxyData.host, proxyData.port, proxyData.username, proxyData.password);
                
                // If proxy doesn't exist, create it
                if (!dolphinProxy) {
                    logFunction(`Creating new proxy in Dolphin Anty: ${proxyData.host}:${proxyData.port}`);
                    try {
                        dolphinProxy = await this.dolphinHelper.createProxy({
                            type: 'http',
                            host: proxyData.host,
                            port: proxyData.port,
                            login: proxyData.username,
                            password: proxyData.password,
                            name: `Task-${taskNumber}-Proxy-${Date.now()}`
                        });
                    } catch (proxyError: any) {
                        // Check for 429 rate limit error
                        if (proxyError.message && proxyError.message.includes('429')) {
                            logFunction('Dolphin API rate limit (429) detected', 'error');
                            return 'DOLPHIN_RATE_LIMIT_429';
                        }
                        throw proxyError;
                    }
                } else {
                    logFunction(`Using existing proxy in Dolphin Anty: ${dolphinProxy.id}`);
                }
                
                const profileName: string = taskNumber ? `FIFA-Task-${taskNumber}-${Date.now()}` : `FIFA-Profile-${Date.now()}`;
                
                // Get platform from settings
                const platform = this.settings.getPlatform();
                const platformVersion = '10' // placeholder gets relplaced by fingerprint

                // Create profile with the Dolphin Anty proxy ID
                let profile: any;
                try {
                    profile = await this.dolphinHelper.createProfile({
                        name: profileName,
                        tags: ['fifa', 'automation'],
                        platform: platform,
                        platformVersion: platformVersion,
                        useRandomProxy: false, // Don't use random proxy
                        customProxy: {
                            id: dolphinProxy.id,
                            teamId: dolphinProxy.teamId,
                            userId: dolphinProxy.userId,
                            name: dolphinProxy.name,
                            type: dolphinProxy.type,
                            host: dolphinProxy.host,
                            port: dolphinProxy.port,
                            login: dolphinProxy.login,
                            password: dolphinProxy.password,
                            changeIpUrl: dolphinProxy.changeIpUrl,
                            provider: dolphinProxy.provider,
                            ip: dolphinProxy.ip,
                            savedByUser: true,
                            browser_profiles_count: dolphinProxy.browser_profiles_count,
                            lastCheck: dolphinProxy.lastCheck,
                            createdAt: dolphinProxy.createdAt,
                            updatedAt: dolphinProxy.updatedAt
                        }
                    });
                } catch (profileError: any) {
                    // Check for 429 rate limit error
                    if (profileError.message && profileError.message.includes('429')) {
                        logFunction('Dolphin API rate limit (429) detected during profile creation', 'error');
                        return 'DOLPHIN_RATE_LIMIT_429';
                    }
                    throw profileError;
                }
                
                if (!profile || !profile.browserProfileId) {
                    throw new Error('Failed to create profile or profile ID not returned');
                }
                
                this.profileId = profile.browserProfileId;
                this.proxyId = dolphinProxy.id; // Store the Dolphin Anty proxy ID
                
                logFunction(`Profile created: ${this.profileId} with proxy ${proxyData.host}:${proxyData.port} (ID: ${dolphinProxy.id})`);
                
                // Try to start the profile with 15s timeout
                const startSuccess = await this.startProfileWithTimeout(logFunction, 15000);
                if (!startSuccess) {
                    // Profile start failed - STOP browser first, then delete profile
                    logFunction(`Profile start failed for proxy ${proxyData.host}:${proxyData.port}, stopping and deleting profile...`, 'warn');
                    try {
                        if (this.profileId) {
                            // CRITICAL: Stop the browser process first to prevent orphaned browsers
                            try {
                                // Add timeout to stop operation to prevent hanging
                                const stopPromise = this.stopProfile(logFunction);
                                const timeoutPromise = new Promise((_, reject) => {
                                    setTimeout(() => reject(new Error('Stop timeout')), 5000); // 5 second timeout
                                });
                                
                                await Promise.race([stopPromise, timeoutPromise]);
                            } catch (stopError: any) {
                                logFunction(`Error stopping failed profile: ${stopError.message}`, 'warn');
                            }
                            
                            // Then delete the profile
                            await this.dolphinHelper.deleteProfile(this.profileId);
                            logFunction(`Deleted failed profile: ${this.profileId}`);
                        }
                    } catch (deleteError: any) {
                        logFunction(`Error deleting failed profile: ${deleteError.message}`, 'warn');
                    }
                    
                    // Reset profile state
                    this.profileId = null;
                    this.proxyId = null;
                    this.browserPath = null;
                    
                    // Continue to next attempt with different proxy
                    continue;
                }
                
                logFunction(`Successfully started profile with proxy ${proxyData.host}:${proxyData.port}`);
                return profile;
                
            } catch (error: any) {
                lastError = error;
                logFunction(`Profile creation attempt ${attempt} failed: ${error.message}`, 'warn');
                
                // Clean up any partial state
                if (this.profileId) {
                    try {
                        await this.deleteProfile(logFunction);
                    } catch (cleanupError: any) {
                        logFunction(`Cleanup error: ${cleanupError.message}`, 'warn');
                    }
                }
                
                // Don't retry for certain errors
                if (error.message.includes('No unused proxies available')) {
                    logFunction('No unused proxies available', 'error');
                    return 'NO_PROXIES_AVAILABLE';
                }
                
                // Small delay before trying next proxy
                if (attempt < maxRetries) {
                    const waitTime = 1000; // 1 second between attempts
                    logFunction(`Waiting ${waitTime}ms before trying next proxy...`);
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                }
            }
        }
        
        logFunction(`Failed to create and start profile after ${maxRetries} attempts with different proxies: ${lastError?.message}`, 'error');
        return false;
    }

    /**
     * Get the last proxy string assigned during createAndStartProfile
     */
    getLastAssignedProxyString(): string | null {
        return this.lastAssignedProxyString;
    }

    /**
     * Start the profile and get browser connection details
     * @param {Function} logFunction - Logging function
     * @returns {Promise<boolean>} Success status
     */
    async startProfile(logFunction: Function): Promise<boolean> {
        try {
            const response = await fetch(`${config.LOCAL_API_BASE_URL}/browser_profiles/${this.profileId}/start?automation=1`, {
                method: 'GET'
            });

            const result = await response.json();
            
            if (result.success && result.automation) {
                this.browserPath = result.automation;
                return true;
            } else {
                logFunction(`Failed to start profile: ${JSON.stringify(result)}`, 'error');
                return false;
            }
        } catch (error: any) {
            logFunction(`Error starting profile: ${error.message}`, 'error');
            return false;
        }
    }

    /**
     * Start the profile with a single timeout attempt
     * @param {Function} logFunction - Logging function
     * @param {number} timeoutMs - Timeout in milliseconds (default: 15000)
     * @returns {Promise<boolean>} Success status
     */
    async startProfileWithTimeout(logFunction: Function, timeoutMs: number = 15000): Promise<boolean> {
        try {
            logFunction(`Starting profile with ${timeoutMs}ms timeout...`);
            
            // Create a timeout promise
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Profile start timeout')), timeoutMs);
            });
            
            // Create the fetch promise
            const fetchPromise = fetch(`${config.LOCAL_API_BASE_URL}/browser_profiles/${this.profileId}/start?automation=1`, {
                method: 'GET'
            });

            // Race between fetch and timeout
            const response = await Promise.race([fetchPromise, timeoutPromise]) as Response;
            
            if (response.status >= 500 && response.status < 600) {
                logFunction(`Got ${response.status} error when starting profile - stopping browser and deleting profile`, 'error');
                
                try {
                    await this.stopProfile(logFunction);
                    logFunction(`Stopped browser after ${response.status} error`);
                } catch (stopError: any) {
                    logFunction(`Error stopping browser after ${response.status} error: ${stopError.message}`, 'warn');
                }
                
                try {
                    if (this.profileId) {
                        await this.dolphinHelper.deleteProfile(this.profileId);
                        logFunction(`Deleted profile after ${response.status} error: ${this.profileId}`);
                    }
                } catch (deleteError: any) {
                    logFunction(`Error deleting profile after ${response.status} error: ${deleteError.message}`, 'warn');
                }
                
                this.profileId = null;
                this.proxyId = null;
                this.browserPath = null;
                
                return false;
            }
            
            const result = await response.json();
            
            if (result.success && result.automation) {
                this.browserPath = result.automation;
                logFunction(`Profile started successfully`);
                return true;
            } else {
                logFunction(`Failed to start profile: ${JSON.stringify(result)}`, 'error');
                return false;
            }
        } catch (error: any) {
            logFunction(`Profile start failed: ${error.message}`, 'error');
            return false;
        }
    }

    /**
     * Start the profile with retry mechanism
     * @param {Function} logFunction - Logging function
     * @param {number} maxRetries - Maximum number of retries (default: 3)
     * @returns {Promise<boolean>} Success status
     */
    async startProfileWithRetry(logFunction: Function, maxRetries: number = 3): Promise<boolean> {
        let lastError: any = null;
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                logFunction(`Starting profile... (Attempt ${attempt}/${maxRetries})`);
                
                // Create a timeout promise
                const timeoutPromise = new Promise((_, reject) => {
                    setTimeout(() => reject(new Error('Profile start timeout')), 45000); // 45 second timeout
                });
                
                // Create the fetch promise
                const fetchPromise = fetch(`${config.LOCAL_API_BASE_URL}/browser_profiles/${this.profileId}/start?automation=1`, {
                    method: 'GET'
                });

                // Race between fetch and timeout
                const response = await Promise.race([fetchPromise, timeoutPromise]) as Response;
                const result = await response.json();
                
                if (result.success && result.automation) {
                    this.browserPath = result.automation;
                    logFunction(`Profile started successfully on attempt ${attempt}`);
                    return true;
                } else {
                    throw new Error(`Failed to start profile: ${JSON.stringify(result)}`);
                }
            } catch (error: any) {
                lastError = error;
                logFunction(`Profile start attempt ${attempt} failed: ${error.message}`, 'warn');
                
                // Wait before retry (exponential backoff)
                if (attempt < maxRetries) {
                    const waitTime = Math.min(2000 * Math.pow(2, attempt - 1), 15000); // Max 15 seconds
                    logFunction(`Waiting ${waitTime}ms before retry...`);
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                }
            }
        }
        
        logFunction(`Failed to start profile after ${maxRetries} attempts: ${lastError?.message}`, 'error');
        return false;
    }

    /**
     * Stop the current profile
     * @param {Function} logFunction - Logging function
     * @returns {Promise<boolean>} Success status
     */
    async stopProfile(logFunction: Function): Promise<boolean> {
        try {
            if (!this.profileId) return true;
            
            //logFunction(`Stopping profile ${this.profileId}...`);
            
            // Add timeout to prevent hanging
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Profile stop timeout')), 10000); // 10 second timeout
            });
            
            const stopPromise = fetch(`${config.LOCAL_API_BASE_URL}/browser_profiles/${this.profileId}/stop`, {
                method: 'GET'
            });
            
            const response = await Promise.race([stopPromise, timeoutPromise]) as Response;
            const result = await response.json();
            
            if (result.success) {
                logFunction('Profile stopped successfully');
                return true;
            } else {
                logFunction(`Failed to stop profile: ${JSON.stringify(result)}`, 'warn');
                return false;
            }
        } catch (error: any) {
            logFunction(`Error stopping profile: ${error.message}`, 'warn');
            return false;
        }
    }

    /**
     * Delete the current profile and its associated proxy
     * @param {Function} logFunction - Logging function
     * @param {boolean} skipStop - Skip stopping the profile (useful when already stopped)
     * @returns {Promise<boolean>} Success status
     */
    async deleteProfile(logFunction: Function, skipStop: boolean = false): Promise<boolean> {
        try {
            if (!this.profileId) return true;
            
            //logFunction(`Deleting profile ${this.profileId}...`);
            
            // Stop profile first (unless already stopped)
            if (!skipStop) {
                await this.stopProfile(logFunction);
            }
            
            // Delete the profile first
            await this.dolphinHelper.deleteProfile(this.profileId);
            //logFunction(`Profile ${this.profileId} deleted`);
            
            // Delete associated proxy from Dolphin Anty if available
            if (this.proxyId) {
                try {
                    await this.dolphinHelper.deleteProxy(this.proxyId);
                    //logFunction(`Deleted proxy ${this.proxyId} from Dolphin Anty`);
                } catch (proxyError: any) {
                    logFunction(`Error deleting proxy ${this.proxyId}: ${proxyError.message}`, 'warn');
                }
            }
            
            // ALWAYS reset state after deletion
            this.profileId = null;
            this.proxyId = null;
            this.browserPath = null;
            
            return true;
        } catch (error: any) {
            logFunction(`Error deleting profile: ${error.message}`, 'warn');
            
            // ALWAYS reset state even on error
            this.profileId = null;
            this.proxyId = null;
            this.browserPath = null;
            
            return false;
        }
    }

    /**
     * Get the browser path for connecting to the profile
     * @returns {string|null} Browser path or null if not available
     */
    getBrowserPath(): string | null {
        return this.browserPath;
    }

    /**
     * Get the profile ID
     * @returns {string|null} Profile ID or null if not available
     */
    getProfileId(): string | null {
        return this.profileId;
    }

    /**
     * Get the proxy ID
     * @returns {string|null} Proxy ID or null if not available
     */
    getProxyId(): string | null {
        return this.proxyId;
    }
}

export default ProfileHelper;