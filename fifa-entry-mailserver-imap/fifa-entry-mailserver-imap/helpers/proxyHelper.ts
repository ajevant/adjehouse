// Types and interfaces
interface ProxyData {
    host: string;
    port: number;
    username: string;
    password: string;
}

/**
 * Proxy Helper - Utility functions for proxy management
 * Contains functions for proxy assignment and parsing
 */
class ProxyHelper {
    /**
     * Assign a unique proxy to this task based on task number
     * @param proxies - Array of proxy strings
     * @param taskNumber - Task number (1-based)
     * @param logFunction - Logging function
     * @returns Assigned proxy string or null if no proxies available
     */
    static assignProxy(proxies: string[], taskNumber: number, logFunction: Function): string | null {
        if (!proxies || proxies.length === 0) {
            logFunction('No proxies available for assignment', 'error');
            return null;
        }
        
        // Use task number to assign proxy (0-based index)
        const proxyIndex: number = (taskNumber - 1) % proxies.length;
        const assignedProxy: string = proxies[proxyIndex].trim();
    
        return assignedProxy;
    }

    /**
     * Parse proxy string into components
     * @param proxyString - Proxy string in format "ip:port:username:password"
     * @param logFunction - Logging function
     * @returns Proxy object or null if invalid
     */
    static parseProxy(proxyString: string, logFunction: Function): ProxyData | null {
        if (!proxyString || typeof proxyString !== 'string') {
            return null;
        }
        
        const parts: string[] = proxyString.trim().split(':');
        if (parts.length !== 4) {
            logFunction(`Invalid proxy format: ${proxyString}`, 'error');
            return null;
        }
        
        return {
            host: parts[0],
            port: parseInt(parts[1]),
            username: parts[2],
            password: parts[3]
        };
    }
}

export default ProxyHelper;
