// Types and interfaces
interface GeneratedAddress {
    FIRST_NAME: string;
    LAST_NAME: string;
    ADDRESS: string;
    CITY: string;
    STATE: string;
    ZIP_CODE: string;
    COUNTRY: string;
    PHONE: string;
    [key: string]: any;
}

interface UserData {
    EMAIL: string;
    PASSWORD: string;
    HAS_ACCOUNT: boolean;
    ADDRESS_COUNTRY: string;
    FAN_OF?: string;
    [key: string]: any;
}

import { generateAddress, generatePhoneNumber } from './addressHelper';

/**
 * Utility Helper - Common utility functions
 * Contains functions for delays, logging, and other utilities
 */
class UtilityHelper {
    /**
     * Generate random delay between min and max milliseconds
     * @param min - Minimum delay in ms
     * @param max - Maximum delay in ms
     * @returns Random delay
     */
    static randomDelay(min: number = 1000, max: number = 3000): number {
        // Create a non-uniform distribution and occasional spikes to increase variance
        // Skew factor between 0.6 and 1.8 - changes per call for extra unpredictability
        const skew = 0.6 + Math.random() * 1.2;
        let r = Math.pow(Math.random(), skew);

        // Occasionally allow slightly extended max to create outliers (7% chance)
        let maxExtended = max;
        if (Math.random() < 0.07) {
            maxExtended = Math.floor(max * (1.15 + Math.random() * 0.25)); // 15-40% extension
        }

        const value = Math.floor(min + r * (maxExtended - min + 1));
        return Math.max(min, Math.min(value, maxExtended));
    }

    /**
     * Log message with task number prefix and optional colors
     * @param message - Message to log
     * @param level - Log level (log, error, warn, success, info)
     * @param taskNumber - Task number for prefix
     */
    static log(message: string, level: string = 'log', taskNumber: number | null = null): void {
        try {
            const taskPrefix: string = taskNumber ? `[TASK-${taskNumber}]` : '[TASK-?]';
            
            // Color codes
            const colors = {
                reset: '\x1b[0m',
                red: '\x1b[31m',
                green: '\x1b[32m',
                yellow: '\x1b[33m',
                blue: '\x1b[34m',
                magenta: '\x1b[35m',
                cyan: '\x1b[36m',
                white: '\x1b[37m',
                bright: '\x1b[1m'
            };
            
            let colorCode: string = '';
            let fullMessage: string = '';
            
            switch (level) {
                case 'error':
                    colorCode = colors.red;
                    fullMessage = `${colorCode}${taskPrefix} ${message}${colors.reset}`;
                    console.error(fullMessage);
                    break;
                case 'warn':
                    colorCode = colors.yellow;
                    fullMessage = `${colorCode}${taskPrefix} ${message}${colors.reset}`;
                    console.warn(fullMessage);
                    break;
                case 'success':
                    colorCode = colors.green;
                    fullMessage = `${colorCode}${taskPrefix} ${message}${colors.reset}`;
                    console.log(fullMessage);
                    break;
                case 'info':
                    colorCode = colors.blue;
                    fullMessage = `${colorCode}${taskPrefix} ${message}${colors.reset}`;
                    console.log(fullMessage);
                    break;
                default:
                    fullMessage = `${taskPrefix} ${message}`;
                    console.log(fullMessage);
            }
        } catch (error: any) {
            console.error(`Error in logging: ${error.message}`);
        }
    }

    /**
     * Generate address data for a user
     * @param user - User data
     * @param retries - Number of retries
     * @param logFunction - Logging function
     * @returns Promise<GeneratedAddress> Generated address data
     */
    static async generateAddressData(user: UserData, retries: number = 3, logFunction: Function = console.log, type: 'entry' | 'account' | 'entry-queuepass' = 'entry'): Promise<GeneratedAddress> {
        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                //logFunction(`Generating address data (attempt ${attempt}/${retries})`);
                
                // Use FAN_OF country if available, otherwise use ADDRESS_COUNTRY
                const countryCode: string = user.ADDRESS_COUNTRY || user.FAN_OF || '';
                if (!countryCode) {
                    throw new Error('No country code provided');
                }
                
                let addressData: GeneratedAddress;
                
                if (type === 'account') {
                    // For account type, skip Mapbox API call and generate minimal data
                    //logFunction(`Generating minimal address data for account type (skipping Mapbox API)`);
                    
                    // Generate random names and basic info without address
                    const firstNames = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Lisa', 'Robert', 'Emily', 'James', 'Jessica'];
                    const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'];
                    
                    addressData = {
                        FIRST_NAME: firstNames[Math.floor(Math.random() * firstNames.length)],
                        LAST_NAME: lastNames[Math.floor(Math.random() * lastNames.length)],
                        ADDRESS: '123 Main St', // Placeholder address
                        CITY: 'City', // Placeholder city
                        STATE: 'State', // Placeholder state
                        ZIP_CODE: '12345', // Placeholder zip
                        COUNTRY: countryCode,
                        PHONE: generatePhoneNumber(countryCode),
                        STREET_AND_NUMBER: '123 Main St',
                        POSTALCODE: '12345'
                    };
                    
                    //logFunction(`Successfully generated minimal address data for account: ${addressData.FIRST_NAME} ${addressData.LAST_NAME}`);
                } else {
                    // For entry type, use full Mapbox API call
                    addressData = await generateAddress(countryCode);
                    logFunction(`Successfully generated full address data ${addressData.STREET_AND_NUMBER}, ${addressData.CITY} ${addressData.POSTALCODE}`);
                }
                
                return addressData;
                
            } catch (error: any) {
                logFunction(`Failed to generate address data (attempt ${attempt}/${retries}): ${error.message}`, 'error');
                
                if (attempt === retries) {
                    throw error;
                }
                
                // Wait before retry
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(1000, 2000)));
            }
        }
        
        throw new Error('Failed to generate address data after all retries');
    }

    /**
     * Format timestamp for logging
     * @returns Formatted timestamp string
     */
    static getTimestamp(): string {
        return new Date().toISOString();
    }

    /**
     * Sleep for specified milliseconds
     * @param ms - Milliseconds to sleep
     * @returns Promise<void>
     */
    static sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Generate random string
     * @param length - Length of string
     * @param charset - Character set to use
     * @returns Random string
     */
    static randomString(length: number, charset: string = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'): string {
        let result = '';
        for (let i = 0; i < length; i++) {
            result += charset.charAt(Math.floor(Math.random() * charset.length));
        }
        return result;
    }

    /**
     * Generate random number between min and max
     * @param min - Minimum value
     * @param max - Maximum value
     * @returns Random number
     */
    static randomNumber(min: number, max: number): number {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    /**
     * Validate email format
     * @param email - Email to validate
     * @returns True if valid email format
     */
    static isValidEmail(email: string): boolean {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    /**
     * Sanitize string for logging
     * @param str - String to sanitize
     * @returns Sanitized string
     */
    static sanitizeForLog(str: string): string {
        if (typeof str !== 'string') {
            return String(str);
        }
        
        // Remove sensitive information patterns
        return str
            .replace(/\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b/g, '****-****-****-****') // Credit card
            .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '***-**-****') // SSN
            .replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, '***@***.***'); // Email
    }

    /**
     * Retry function with exponential backoff
     * @param fn - Function to retry
     * @param maxRetries - Maximum number of retries
     * @param baseDelay - Base delay in ms
     * @returns Promise<any> Result of function
     */
    static async retryWithBackoff<T>(
        fn: () => Promise<T>, 
        maxRetries: number = 3, 
        baseDelay: number = 1000
    ): Promise<T> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                return await fn();
            } catch (error: any) {
                if (attempt === maxRetries) {
                    throw error;
                }
                
                const delay: number = baseDelay * Math.pow(2, attempt - 1);
                await this.sleep(delay);
            }
        }
        
        throw new Error('Retry failed');
    }
}

export default UtilityHelper;
