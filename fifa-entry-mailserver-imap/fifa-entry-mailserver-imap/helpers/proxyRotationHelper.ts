// Types and interfaces
interface ProxyData {
    id: string;
    teamId: string;
    userId: string;
    name: string;
    type: string;
    host: string;
    port: number;
    login: string;
    password: string;
    changeIpUrl: string;
    provider: string;
    ip: string;
    savedByUser: boolean;
    browser_profiles_count: number;
    lastCheck: any;
    createdAt: string;
    updatedAt: string;
}

interface ProxyResponse {
    data: ProxyData[];
}

interface RotationResult {
    success: boolean;
    newProxyId: string;
    newProxy: ProxyData;
}

/**
 * Proxy Rotation Helper
 * Handles proxy updates and profile rotation when CAPTCHA is detected
 */
class ProxyRotationHelper {
    private apiToken: string;
    private log: (message: string) => void;
    private baseUrl: string;

    constructor(apiToken: string, logFunction?: (message: string) => void) {
        this.apiToken = apiToken;
        this.log = logFunction || console.log;
        this.baseUrl = 'https://dolphin-anty-api.com';
    }

    /**
     * Update browser profile with new proxy
     */
    async updateProfileProxy(profileId: string, newProxyId: string): Promise<boolean> {
        try {
            this.log(`Updating profile ${profileId} with new proxy ${newProxyId}...`);
            
            const response = await fetch(
                `${this.baseUrl}/browser_profiles/${profileId}`,
                {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiToken}`
                    },
                    body: JSON.stringify({
                        proxyId: newProxyId
                    })
                }
            );

            if (response.status === 200) {
                this.log(`Profile ${profileId} updated with new proxy ${newProxyId}`);
                return true;
            } else {
                this.log(`❌ Failed to update profile: ${response.status}`);
                return false;
            }

        } catch (error: any) {
            this.log(`❌ Error updating profile proxy: ${error.message}`);
            if (error.response) {
                this.log(`❌ Response status: ${error.response.status}`);
                this.log(`❌ Response data: ${JSON.stringify(error.response.data)}`);
            }
            return false;
        }
    }

    /**
     * Delete old proxy
     */
    async deleteProxy(proxyId: string): Promise<boolean> {
        try {
            this.log(`🗑️ Deleting old proxy ${proxyId}...`);
            
            const response = await fetch(
                `${this.baseUrl}/proxies/${proxyId}`,
                {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${this.apiToken}`
                    }
                }
            );

            if (response.status === 200) {
                //this.log(`Proxy ${proxyId} deleted successfully`);
                return true;
            } else {
                this.log(`❌ Failed to delete proxy: ${response.status}`);
                return false;
            }

        } catch (error: any) {
            this.log(`❌ Error deleting proxy: ${error.message}`);
            if (error.response) {
                this.log(`❌ Response status: ${error.response.status}`);
                this.log(`❌ Response data: ${JSON.stringify(error.response.data)}`);
            }
            return false;
        }
    }

    /**
     * Get available proxies
     */
    async getAvailableProxies(): Promise<ProxyData[]> {
        try {
            this.log(`🔍 Fetching available proxies...`);
            
            const response = await fetch(
                `${this.baseUrl}/proxies`,
                {
                    headers: {
                        'Authorization': `Bearer ${this.apiToken}`
                    }
                }
            );

            if (response.status === 200) {
                const data = await response.json();
                if (data.data) {
                    const proxies: ProxyData[] = data.data;
                    this.log(`Found ${proxies.length} available proxies`);
                    return proxies;
                } else {
                    this.log(`❌ No proxy data found in response`);
                    return [];
                }
            } else {
                this.log(`❌ Failed to fetch proxies: ${response.status}`);
                return [];
            }

        } catch (error: any) {
            this.log(`❌ Error fetching proxies: ${error.message}`);
            if (error.response) {
                this.log(`❌ Response status: ${error.response.status}`);
                this.log(`❌ Response data: ${JSON.stringify(error.response.data)}`);
            }
            return [];
        }
    }

    /**
     * Get a random available proxy (excluding current one)
     */
    async getRandomProxy(excludeProxyId: string | null = null): Promise<ProxyData | null> {
        try {
            const proxies: ProxyData[] = await this.getAvailableProxies();
            
            if (proxies.length === 0) {
                this.log(`❌ No proxies available`);
                return null;
            }

            // Filter out the current proxy if specified
            const availableProxies: ProxyData[] = excludeProxyId 
                ? proxies.filter(proxy => proxy.id !== excludeProxyId)
                : proxies;

            if (availableProxies.length === 0) {
                this.log(`❌ No other proxies available (excluding ${excludeProxyId})`);
                return null;
            }

            // Get random proxy
            const randomIndex: number = Math.floor(Math.random() * availableProxies.length);
            const selectedProxy: ProxyData = availableProxies[randomIndex];
            
            this.log(`🎯 Selected random proxy: ${selectedProxy.id} (${selectedProxy.host}:${selectedProxy.port})`);
            return selectedProxy;

        } catch (error: any) {
            this.log(`❌ Error getting random proxy: ${error.message}`);
            return null;
        }
    }

    /**
     * Rotate proxy for a profile (main function)
     */
    async rotateProxy(profileId: string, currentProxyId: string | null): Promise<RotationResult | false> {
        try {
            this.log(`Starting proxy rotation for profile ${profileId}...`);
            
            // Get a new random proxy
            const newProxy: ProxyData | null = await this.getRandomProxy(currentProxyId);
            if (!newProxy) {
                this.log(`❌ No new proxy available for rotation`);
                return false;
            }

            // Update profile with new proxy
            const updateSuccess: boolean = await this.updateProfileProxy(profileId, newProxy.id);
            if (!updateSuccess) {
                this.log(`❌ Failed to update profile with new proxy`);
                return false;
            }

            // Delete old proxy
            if (currentProxyId) {
                const deleteSuccess: boolean = await this.deleteProxy(currentProxyId);
                if (!deleteSuccess) {
                    this.log(`⚠️ Failed to delete old proxy, but profile was updated`);
                }
            }

            this.log(`Proxy rotation completed successfully`);
            this.log(`   Old proxy: ${currentProxyId}`);
            this.log(`   New proxy: ${newProxy.id} (${newProxy.host}:${newProxy.port})`);
            
            return {
                success: true,
                newProxyId: newProxy.id,
                newProxy: newProxy
            };

        } catch (error: any) {
            this.log(`❌ Error during proxy rotation: ${error.message}`);
            return false;
        }
    }
}

export default ProxyRotationHelper;
