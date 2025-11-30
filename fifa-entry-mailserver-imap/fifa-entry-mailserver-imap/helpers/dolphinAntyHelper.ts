import * as proxyManager from './proxyManager';
import * as profileCreator from './profileCreator';
import config from './config';
import SettingsHelper from './settingsHelper';

// Initialize settings helper (singleton)
const settings = SettingsHelper.getInstance();

// Your Dolphin Anty token (from settings.txt)
const API_TOKEN = settings.get('DOLPHYN_API_TOKEN');

/**
 * Main Dolphin Anty API helper class
 */
class DolphinAntyHelper {
    private proxyManager: any;
    private profileCreator: any;

    constructor() {
        this.proxyManager = proxyManager;
        this.profileCreator = profileCreator;
    }

    /**
     * Get all available proxies
     * @returns {Promise<Object>} Proxy list response
     */
    async getAllProxies(): Promise<any> {
        return await this.proxyManager.getAllProxies();
    }

    /**
     * Get an unused proxy
     * @returns {Promise<Object|null>} Unused proxy or null
     */
    async getUnusedProxy(): Promise<any | null> {
        return await this.proxyManager.getUnusedProxy();
    }

    /**
     * Get a random unused proxy
     * @returns {Promise<Object|null>} Random unused proxy or null
     */
    async getRandomUnusedProxy(): Promise<any | null> {
        return await this.proxyManager.getRandomUnusedProxy();
    }

    /**
     * Create a single profile with timeout handling
     * @param {Object} options - Profile creation options
     * @returns {Promise<Object>} Created profile response
     */
    async createProfile(options: any = {}): Promise<any> {
        // Create a timeout promise
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('Profile creation timeout')), 60000); // 60 second timeout
        });
        
        // Create the profile creation promise
        const createPromise = this.profileCreator.createProfile(options);
        
        // Race between creation and timeout
        return await Promise.race([createPromise, timeoutPromise]) as any;
    }

    /**
     * Create multiple profiles
     * @param {number} count - Number of profiles to create
     * @param {Object} baseOptions - Base options for all profiles
     * @returns {Promise<Array>} Array of created profiles
     */
    async createMultipleProfiles(count: number = 1, baseOptions: any = {}): Promise<any[]> {
        return await this.profileCreator.createMultipleProfiles(count, baseOptions);
    }

    /**
     * Get user agent for a specific configuration
     * @param {string} browserType - Browser type
     * @param {string} browserVersion - Browser version
     * @param {string} platform - Platform
     * @returns {Promise<string>} User agent string
     */
    async getUserAgent(browserType: string = "anty", browserVersion: string = "140", platform: string = "macos"): Promise<string> {
        return await this.profileCreator.getUserAgent(browserType, browserVersion, platform);
    }

    /**
     * Get WebGL information
     * @param {string} browserType - Browser type
     * @param {string} platform - Platform
     * @returns {Promise<Object>} WebGL information
     */
    async getWebGLInfo(browserType: string = "anty", platform: string = "macos"): Promise<any> {
        return await this.profileCreator.getWebGLInfo(browserType, platform);
    }

    /**
     * Get font list
     * @param {string} platform - Platform
     * @returns {Promise<Array>} Font list
     */
    async getFontList(platform: string = "macos"): Promise<any[]> {
        return await this.profileCreator.getFontList(platform);
    }

    /**
     * Create a profile with specific proxy
     * @param {Object} options - Profile creation options
     * @param {Object} proxy - Specific proxy to use
     * @returns {Promise<Object>} Created profile response
     */
    async createProfileWithProxy(options: any = {}, proxy: any): Promise<any> {
        const profileOptions = {
            ...options,
            useRandomProxy: false,
            customProxy: proxy
        };
        return await this.profileCreator.createProfile(profileOptions);
    }

    /**
     * Get proxy usage statistics
     * @returns {Promise<Object>} Proxy usage statistics
     */
    async getProxyStats(): Promise<any> {
        try {
            const proxyResponse = await this.getAllProxies();
            const proxies = proxyResponse.data;
            
            const stats = {
                total: proxies.length,
                used: proxies.filter((p: any) => p.browser_profiles_count > 0).length,
                unused: proxies.filter((p: any) => p.browser_profiles_count === 0).length,
                usageRate: (proxies.filter((p: any) => p.browser_profiles_count > 0).length / proxies.length * 100).toFixed(2) + '%'
            };
            
            return stats;
        } catch (error: any) {
            console.error('Error getting proxy stats:', error.message);
            throw error;
        }
    }

    /**
     * Get profile information by ID
     * @param {string|number} profileId - Profile ID
     * @returns {Promise<Object>} Profile information
     */
    async getProfile(profileId: string | number): Promise<any> {
        try {
            const response = await fetch(`${config.API_BASE_URL}/browser_profiles/${profileId}`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${API_TOKEN}`,
                    'Content-Type': 'application/json'
                }
            });

            // Check for 429 rate limit error
            if (response.status === 429) {
                throw new Error(`Dolphin API rate limit (429) - too many requests`);
            }

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
            }

            const result = await response.json();
            return result;
        } catch (error: any) {
            console.error(`Error fetching profile ${profileId}:`, error.message);
            throw error;
        }
    }

    /**
     * Delete a browser profile
     * @param {string|number} profileId - Profile ID to delete
     * @param {string} password - Password for deletion (optional, uses default from config)
     * @param {boolean} forceDelete - Force delete even if profile is in use (default: true)
     * @returns {Promise<Object>} Deletion response
     */
    async deleteProfile(profileId: string | number, password: string | null = null, forceDelete: boolean = true): Promise<any> {
        try {
            //console.log(`Deleting profile ${profileId}...`);
            
            const deletePassword = password || config.DEFAULT_PROFILE_CONFIG.deletePassword;
            if (!deletePassword) {
                throw new Error('No delete password provided');
            }

            const response = await fetch(`${config.API_BASE_URL}/browser_profiles/${profileId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${API_TOKEN}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    password: deletePassword,
                    forceDelete: forceDelete
                })
            });

            // Check for 429 rate limit error
            if (response.status === 429) {
                throw new Error(`Dolphin API rate limit (429) - too many requests`);
            }

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
            }

            const result = await response.json();
            
            if (result.success) {
                //console.log(`Profile ${profileId} deleted successfully`);
                return result;
            } else {
                throw new Error(`Profile deletion failed: ${JSON.stringify(result)}`);
            }
        } catch (error: any) {
            console.error(`Error deleting profile ${profileId}:`, error.message);
            throw error;
        }
    }

    /**
     * Create a new proxy in Dolphin Anty with timeout handling
     * @param {Object} proxyData - Proxy data
     * @returns {Promise<Object>} Created proxy response
     */
    async createProxy(proxyData: any): Promise<any> {
        try {
            // Create a timeout promise
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Proxy creation timeout')), 30000); // 30 second timeout
            });
            
            // Create the fetch promise
            const fetchPromise = fetch(`${config.API_BASE_URL}/proxy`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${API_TOKEN}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    type: proxyData.type || 'http',
                    host: proxyData.host,
                    port: proxyData.port,
                    login: proxyData.login || '',
                    password: proxyData.password || '',
                    name: proxyData.name || `Proxy-${proxyData.host}-${proxyData.port}`,
                    changeIpUrl: proxyData.changeIpUrl || '',
                    provider: proxyData.provider || ''
                })
            });

            // Race between fetch and timeout
            const response = await Promise.race([fetchPromise, timeoutPromise]) as Response;

            // Check for 429 rate limit error
            if (response.status === 429) {
                throw new Error(`Dolphin API rate limit (429) - too many requests`);
            }

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
            }

            const result = await response.json();
            
            // Check if proxy was created successfully (has an ID)
            if (result.data && result.data.id) {
                return result.data;
            } else {
                throw new Error(`Proxy creation failed: ${JSON.stringify(result)}`);
            }
        } catch (error: any) {
            console.error(`Error creating proxy:`, error.message);
            throw error;
        }
    }

    /**
     * Create multiple proxies from proxy strings
     * @param {Array<string>} proxyStrings - Array of proxy strings in format "ip:port:username:password"
     * @returns {Promise<Array>} Array of created proxy objects with IDs
     */
    async createProxiesFromStrings(proxyStrings: string[]): Promise<any[]> {
        const createdProxies: any[] = [];
        
        for (const proxyString of proxyStrings) {
            try {
                // Parse proxy string
                const parts = proxyString.trim().split(':');
                if (parts.length !== 4) {
                    console.error(`Invalid proxy format: ${proxyString}`);
                    continue;
                }
                
                const proxyData = {
                    type: 'http',
                    host: parts[0],
                    port: parseInt(parts[1]),
                    login: parts[2],
                    password: parts[3],
                    name: `Proxy-${parts[0]}-${parts[1]}`
                };
                
                const createdProxy = await this.createProxy(proxyData);
                createdProxies.push(createdProxy);
                
            } catch (error: any) {
                console.error(`Failed to create proxy from string ${proxyString}:`, error.message);
            }
        }
        
        return createdProxies;
    }

    /**
     * Get proxy by host and port
     * @param {string} host - Proxy host
     * @param {number} port - Proxy port
     * @returns {Promise<Object|null>} Proxy object or null if not found
     */
    async getProxyByHostPort(host: string, port: number): Promise<any | null> {
        try {
            const response = await this.getAllProxies();
            const proxies = response.data;
            
            const proxy = proxies.find((p: any) => p.host === host && parseInt(p.port) === port);
            return proxy || null;
        } catch (error: any) {
            console.error(`Error finding proxy ${host}:${port}:`, error.message);
            return null;
        }
    }

    /**
     * Get proxy by full credentials (host, port, username, password)
     * @param {string} host - Proxy host
     * @param {number} port - Proxy port
     * @param {string} username - Proxy username
     * @param {string} password - Proxy password
     * @returns {Promise<Object|null>} Proxy object or null if not found
     */
    async getProxyByCredentials(host: string, port: number, username: string, password: string): Promise<any | null> {
        try {
            const response = await this.getAllProxies();
            const proxies = response.data;
            
            const proxy = proxies.find((p: any) => 
                p.host === host && 
                parseInt(p.port) === port && 
                p.login === username && 
                p.password === password
            );
            return proxy || null;
        } catch (error: any) {
            console.error(`Error finding proxy ${host}:${port}:${username}:`, error.message);
            return null;
        }
    }

    /**
     * Delete a proxy
     * @param {string|number} proxyId - Proxy ID to delete
     * @returns {Promise<Object>} Deletion response
     */
    async deleteProxy(proxyId: string | number): Promise<any> {
        try {
            //console.log(`Deleting proxy ${proxyId}...`);
            
            const response = await fetch(`${config.API_BASE_URL}/proxy/${proxyId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${API_TOKEN}`,
                    'Content-Type': 'application/json'
                }
            });

            // Check for 429 rate limit error
            if (response.status === 429) {
                throw new Error(`Dolphin API rate limit (429) - too many requests`);
            }

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
            }

            const result = await response.json();
            
            if (result.success) {
               // console.log(`Proxy ${proxyId} deleted successfully`);
                return result;
            } else {
                throw new Error(`Proxy deletion failed: ${JSON.stringify(result)}`);
            }
        } catch (error: any) {
            console.error(`Error deleting proxy ${proxyId}:`, error.message);
            throw error;
        }
    }


}

export default DolphinAntyHelper;