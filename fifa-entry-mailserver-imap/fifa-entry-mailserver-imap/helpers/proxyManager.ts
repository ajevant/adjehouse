import config from './config';
import SettingsHelper from './settingsHelper';

// Initialize settings helper (singleton)
const settings = SettingsHelper.getInstance();

// Your Dolphin Anty token (from settings.txt)
const API_TOKEN = settings.get('DOLPHYN_API_TOKEN');

// API base URL
const API_BASE_URL = config.API_BASE_URL;

/**
 * Get all proxies from Dolphin Anty API
 * @returns {Promise<Object>} Response containing proxy list
 */
async function getAllProxies(): Promise<any> {
    try {
        const response = await fetch(`${API_BASE_URL}/proxy`, {
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
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        return result;
    } catch (error: any) {
        console.error('Error fetching proxies:', error.message);
        throw error;
    }
}

/**
 * Get an unused proxy (browser_profiles_count = 0)
 * @returns {Promise<Object|null>} Unused proxy object or null if none found
 */
async function getUnusedProxy(): Promise<any | null> {
    try {
        const proxyResponse = await getAllProxies();
        const proxies = proxyResponse.data;
        
        // Find first proxy with browser_profiles_count = 0
        const unusedProxy = proxies.find((proxy: any) => proxy.browser_profiles_count === 0);
        
        if (unusedProxy) {
            console.log(`Found unused proxy: ${unusedProxy.name}`);
            return unusedProxy;
        } else {
            console.log('No unused proxies found');
            return null;
        }
    } catch (error: any) {
        console.error('Error getting unused proxy:', error.message);
        throw error;
    }
}

/**
 * Get a random unused proxy
 * @returns {Promise<Object|null>} Random unused proxy object or null if none found
 */
async function getRandomUnusedProxy(): Promise<any | null> {
    try {
        const proxyResponse = await getAllProxies();
        const proxies = proxyResponse.data;
        
        // Filter unused proxies
        const unusedProxies = proxies.filter((proxy: any) => proxy.browser_profiles_count === 0);
        
        if (unusedProxies.length === 0) {
            console.log('No unused proxies found');
            return null;
        }
        
        // Get random proxy
        const randomIndex = Math.floor(Math.random() * unusedProxies.length);
        const randomProxy = unusedProxies[randomIndex];
        
        console.log(`Selected random unused proxy: ${randomProxy.name}`);
        return randomProxy;
    } catch (error: any) {
        console.error('Error getting random unused proxy:', error.message);
        throw error;
    }
}

export {
    getAllProxies,
    getUnusedProxy,
    getRandomUnusedProxy
};