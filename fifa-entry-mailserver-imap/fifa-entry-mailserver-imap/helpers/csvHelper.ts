import * as fs from 'fs';
import * as path from 'path';

/**
 * CSV Helper for reading and managing user information
 */
const colors = {
    green: '\x1b[32m',
    reset: '\x1b[0m'
};

interface UserData {
    EMAIL: string;
    PASSWORD?: string;
    RECEIVINGEMAIL?: string;
    FAN_OF?: string;
    ADDRESS_COUNTRY?: string;
    FIRST_NAME?: string;
    LAST_NAME?: string;
    STREET_AND_NUMBER?: string;
    POSTALCODE?: string;
    CITY?: string;
    STATE?: string;
    PHONE_NUMBER?: string;
    CARD_NUM?: string;
    EXPIRY_MONTH?: string;
    EXPIRY_YEAR?: string;
    CARD_CVV?: string;
    HAS_ACCOUNT?: boolean | string;
    ENTERED?: boolean | string;
    VERIFIED?: boolean | string;
    OTP_ISSUE?: boolean | string;
}

class CsvHelper {
    private static instance: CsvHelper | null = null;
    private csvFilePath: string;
    private data: UserData[];
    private currentIndex: number;

    private constructor(csvFilePath: string | null = null) {
        // If no path provided, look for information.csv in the same directory as the executable
        if (!csvFilePath) {
            let execDir: string;
            
            if ((process as any).pkg) {
                // For packaged executables, ALWAYS use the directory where the exe is located
                execDir = path.dirname(process.execPath);
            } else {
                // For development, use current working directory
                execDir = process.cwd();
            }
            
            this.csvFilePath = path.join(execDir, 'information.csv');
        } else {
            this.csvFilePath = csvFilePath;
        }
        
        this.data = [];
        this.currentIndex = 0;
    }

    /**
     * Get the singleton instance of CsvHelper
     * @param {string|null} csvFilePath - Optional CSV file path
     * @returns {CsvHelper} Singleton instance
     */
    public static getInstance(csvFilePath: string | null = null): CsvHelper {
        if (!CsvHelper.instance) {
            CsvHelper.instance = new CsvHelper(csvFilePath);
        }
        return CsvHelper.instance;
    }


    /**
     * Convert string boolean values to actual boolean
     * @param {string} value - String value to convert
     * @returns {boolean|string} Boolean value or original string if not a boolean
     */
    static parseBoolean(value: any): boolean | string {
        if (typeof value !== 'string') {
            return value;
        }
        
        const normalizedValue = value.trim().toLowerCase();
        
        // True values
        if (['true', 't', '1', 'yes', 'y', 'on'].includes(normalizedValue)) {
            return true;
        }
        
        // False values
        if (['false', 'f', '0', 'no', 'n', 'off'].includes(normalizedValue)) {
            return false;
        }
        
        // Return original value if not a recognized boolean
        return value;
    }

    /**
     * Read and parse CSV file
     * @returns {Promise<Array>} Array of user objects
     */
    async readCsvData(log: boolean = true): Promise<UserData[]> {
        try {
            
            if (!fs.existsSync(this.csvFilePath)) {
                throw new Error(`CSV file not found: ${this.csvFilePath}`);
            }

            const csvContent = fs.readFileSync(this.csvFilePath, 'utf8');
            const lines = csvContent.trim().split('\n');
            
            if (lines.length < 2) {
                throw new Error('CSV file must have at least a header and one data row');
            }

            // Parse header
            const headers = lines[0].split(',').map(h => h.trim());
            
            // Ensure OTP_ISSUE column exists
            if (!headers.includes('OTP_ISSUE')) {
                headers.push('OTP_ISSUE');
            }
            
            // Parse data rows
            this.data = lines.slice(1).map((line, index) => {
                const values = line.split(',').map(v => v.trim());
                
                // Pad values array if it's shorter than headers (for new columns)
                while (values.length < headers.length) {
                    values.push('');
                }
                
                if (values.length !== headers.length) {
                    console.warn(`Row ${index + 2} has ${values.length} columns, expected ${headers.length}`);
                }

                const user: UserData = {} as UserData;
                headers.forEach((header, i) => {
                    const value = values[i] || '';
                    
                    // Convert boolean fields to actual booleans
                    if (['HAS_ACCOUNT', 'ENTERED', 'VERIFIED', 'OTP_ISSUE'].includes(header)) {
                        // Handle empty values for boolean fields
                        if (value === '' || value === undefined || value === null) {
                            (user as any)[header] = false; // Default to false for empty values
                        } else {
                            (user as any)[header] = CsvHelper.parseBoolean(value);
                        }
                    } else {
                        (user as any)[header] = value;
                    }
                });
                
                return user;
            });

            if(log){
                console.log(`${colors.green}Loaded ${this.data.length} tasks from CSV${colors.reset}`);
            }
            return this.data;
        } catch (error: any) {
            console.error('Error reading CSV file:', error.message);
            throw error;
        }
    }

    /**
     * Get a specific user by index (skips users with ENTERED = TRUE)
     * @param {number} index - User index (0-based, among non-entered users)
     * @returns {Object|null} User object or null if not found
     */
    getUserByIndex(index: number): UserData | null {
        // Get only users who haven't entered yet
        const availableUsers = this.data.filter(user => 
            !user.ENTERED || user.ENTERED !== true
        );
        
        console.log(`Total users: ${this.data.length}, Available (not entered): ${availableUsers.length}`);
        
        if (index >= 0 && index < availableUsers.length) {
            const selectedUser = availableUsers[index];
            const originalIndex = this.data.indexOf(selectedUser);
            console.log(`Selected user at available index ${index} (original index ${originalIndex}): ${selectedUser.EMAIL}`);
            return selectedUser;
        }
        
        console.log(`Index ${index} not found in available users (${availableUsers.length} available)`);
        return null;
    }

    /**
     * Get a specific user by original index (ignores ENTERED status)
     * @param {number} index - Original user index (0-based)
     * @returns {Object|null} User object or null if not found
     */
    getUserByOriginalIndex(index: number): UserData | null {
        if (index >= 0 && index < this.data.length) {
            return this.data[index];
        }
        return null;
    }

    /**
     * Get the next user in sequence (skips users with ENTERED = TRUE)
     * @returns {Object|null} Next user object or null if no more users
     */
    getNextUser(): UserData | null {
        // Get only users who haven't entered yet
        const availableUsers = this.data.filter(user => 
            !user.ENTERED || user.ENTERED !== true
        );
        
        if (this.currentIndex < availableUsers.length) {
            const user = availableUsers[this.currentIndex];
            this.currentIndex++;
            const originalIndex = this.data.indexOf(user);
            console.log(`Next available user (${this.currentIndex-1}/${availableUsers.length}) - original index ${originalIndex}: ${user.EMAIL}`);
            return user;
        }
        
        console.log(`No more available users (${availableUsers.length} total available)`);
        return null;
    }

    /**
     * Get a random user (skips users with ENTERED = TRUE)
     * @returns {Object|null} Random user object or null if no users
     */
    getRandomUser(): UserData | null {
        // Get only users who haven't entered yet
        const availableUsers = this.data.filter(user => 
            !user.ENTERED || user.ENTERED !== true
        );
        
        if (availableUsers.length === 0) {
            console.log('No available users for random selection');
            return null;
        }
        
        const randomIndex = Math.floor(Math.random() * availableUsers.length);
        const selectedUser = availableUsers[randomIndex];
        const originalIndex = this.data.indexOf(selectedUser);
        console.log(`Random user selected (available index ${randomIndex}, original index ${originalIndex}): ${selectedUser.EMAIL}`);
        return selectedUser;
    }

    /**
     * Get all users
     * @returns {Array} Array of all user objects
     */
    getAllUsers(): UserData[] {
        return this.data;
    }

    /**
     * Get total number of users
     * @returns {number} Total user count
     */
    getUserCount(): number {
        return this.data.length;
    }

    /**
     * Get number of available users (not entered)
     * @returns {number} Available user count
     */
    getAvailableUserCount(): number {
        const availableUsers = this.data.filter(user => 
            !user.ENTERED || user.ENTERED !== true
        );
        return availableUsers.length;
    }

    /**
     * Get all available users (not entered)
     * @returns {Array} Array of available user objects
     */
    getAvailableUsers(type: 'entry' | 'account' | 'entry-fifa-com' | 'entry-queuepass' = 'entry'): UserData[] {
        return this.data.filter(user => {
            // Skip if already entered
            if (user.ENTERED === true) {
                return false;
            }
            
            // Skip if has OTP issues
            if (user?.OTP_ISSUE === true) {
                return false;
            }
            
            if(type === 'account'){
                // For account generation, skip if already verified
                if (user.VERIFIED === true) {
                    return false;
                }
            }
            
            return true;
        });
    }

    /**
     * Get statistics about users
     * @returns {Object} Statistics object
     */
    getUserStats(): any {
        const total = this.data.length;
        const entered = this.data.filter(user => 
            user.ENTERED === true
        ).length;
        const available = total - entered;
        
        return {
            total,
            entered,
            available,
            percentageCompleted: total > 0 ? Math.round((entered / total) * 100) : 0
        };
    }

    /**
     * Reset the current index to start from the beginning
     */
    resetIndex(): void {
        this.currentIndex = 0;
    }

    /**
     * Get current index
     * @returns {number} Current index
     */
    getCurrentIndex(): number {
        return this.currentIndex;
    }

    /**
     * Check if there are more available users (not entered)
     * @returns {boolean} True if more users available
     */
    hasMoreUsers(): boolean {
        const availableUsers = this.data.filter(user => 
            !user.ENTERED || user.ENTERED !== true
        );
        return this.currentIndex < availableUsers.length;
    }

    /**
     * Get users by batch (for bulk processing)
     * @param {number} batchSize - Number of users per batch
     * @returns {Array} Array of user batches
     */
    getUsersInBatches(batchSize: number = 5): UserData[][] {
        const batches: UserData[][] = [];
        for (let i = 0; i < this.data.length; i += batchSize) {
            batches.push(this.data.slice(i, i + batchSize));
        }
        return batches;
    }

    /**
     * Validate user data
     * @param {Object} user - User object to validate
     * @returns {Object} Validation result
     */
    validateUser(user: UserData): any {
        const requiredFields = ['EMAIL', 'FIRST_NAME', 'LAST_NAME', 'STREET_AND_NUMBER', 'POSTALCODE', 'CITY', 'CARD_NUM', 'EXPIRY_MONTH', 'EXPIRY_YEAR', 'CARD_CVV', 'PHONE_NUMBER', 'HAS_ACCOUNT', 'ENTERED'];
        const missing: string[] = [];
        const invalid: string[] = [];

        // Check for missing fields
        requiredFields.forEach(field => {
            if (!(user as any)[field] || (user as any)[field].toString().trim() === '') {
                missing.push(field);
            }
        });

        // Basic validation for specific fields
        if (user.EMAIL && !user.EMAIL.includes('@')) {
            invalid.push('EMAIL');
        }

        if (user.CARD_NUM && user.CARD_NUM.length < 13) {
            invalid.push('CARD_NUM');
        }

        if (user.CARD_CVV && (user.CARD_CVV.length < 3 || user.CARD_CVV.length > 4)) {
            invalid.push('CARD_CVV');
        }

        if (user.EXPIRY_MONTH && (parseInt(user.EXPIRY_MONTH) < 1 || parseInt(user.EXPIRY_MONTH) > 12)) {
            invalid.push('EXPIRY_MONTH');
        }

        if (user.EXPIRY_YEAR && (parseInt(user.EXPIRY_YEAR) < 2024 || parseInt(user.EXPIRY_YEAR) > 2030)) {
            invalid.push('EXPIRY_YEAR');
        }

        if (user.HAS_ACCOUNT !== undefined && typeof user.HAS_ACCOUNT !== 'boolean') {
            invalid.push('HAS_ACCOUNT');
        }

        if (user.ENTERED !== undefined && typeof user.ENTERED !== 'boolean') {
            invalid.push('ENTERED');
        }

        return {
            isValid: missing.length === 0 && invalid.length === 0,
            missing,
            invalid,
            user
        };
    }

    /**
     * Get validation summary for all users
     * @returns {Object} Validation summary
     */
    getValidationSummary(): any {
        const valid: any[] = [];
        const invalid: any[] = [];

        this.data.forEach((user, index) => {
            const validation = this.validateUser(user);
            if (validation.isValid) {
                valid.push({ index, user });
            } else {
                invalid.push({ index, user, ...validation });
            }
        });

        return {
            total: this.data.length,
            valid: valid.length,
            invalid: invalid.length,
            validUsers: valid,
            invalidUsers: invalid
        };
    }

    /**
     * Print user information in a formatted way
     * @param {Object} user - User object to print
     */
    printUserInfo(user: UserData): void {
        console.log('\nUser Information:');
        console.log(`Email: ${user.EMAIL}`);
        console.log(`Name: ${user.FIRST_NAME} ${user.LAST_NAME}`);
        console.log(`Address: ${user.STREET_AND_NUMBER}, ${user.POSTALCODE} ${user.CITY || 'N/A'}`);
        console.log(`Card: ${user.CARD_NUM} (${user.CARD_CVV}) - Expires: ${user.EXPIRY_MONTH || 'N/A'}/${user.EXPIRY_YEAR || 'N/A'}`);
        console.log(`Phone: ${user.PHONE_NUMBER}`);
        console.log(`Has Account: ${user.HAS_ACCOUNT || 'Not specified'}`);
        console.log(`Entered: ${user.ENTERED || 'Not specified'}`);
    }

    /**
     * Update a user's data in memory and save to CSV
     * @param {string} email - User's email (unique identifier)
     * @param {Object} updates - Object with fields to update
     * @returns {Promise<boolean>} Success status
     */
    async updateUser(email: string, updates: any): Promise<boolean> {
        try {
            
            // Find user by email
            const userIndex = this.data.findIndex(user => user.EMAIL === email);
            if (userIndex === -1) {
                console.log(`User not found with email: ${email}`);
                return false;
            }

            // Update user data in memory
            Object.keys(updates).forEach(key => {
                (this.data[userIndex] as any)[key] = updates[key];
                //console.log(`Updated ${key}: ${updates[key]}`);
            });

            // Save to CSV file
            await this.writeCsvData();
            return true;

        } catch (error: any) {
            console.error('Error updating user:', error.message);
            return false;
        }
    }

    /**
     * Mark a user as blocked
     * @param {string} email - User's email
     * @returns {Promise<boolean>} Success status
     */
    async markUserBlocked(email: string): Promise<boolean> {
        return await this.updateUser(email, { BLOCKED: true });
    }

    /**
     * Check if user is blocked
     * @param {Object} user - User data object
     * @returns {boolean} True if user is blocked
     */
    static isBlocked(user: UserData): boolean {
        if ((user as any).BLOCKED === undefined || (user as any).BLOCKED === null) {
            return false; // Default to false if not specified
        }
        
        // If it's already a boolean, return it
        if (typeof (user as any).BLOCKED === 'boolean') {
            return (user as any).BLOCKED;
        }
        
        // If it's still a string (for backward compatibility), parse it
        const blocked = (user as any).BLOCKED.toString().toLowerCase();
        return blocked === 'true' || blocked === '1' || blocked === 'yes';
    }

    /**
     * Update HAS_ACCOUNT to TRUE for a user
     * @param {string} email - User's email
     * @returns {Promise<boolean>} Success status
     */
    async markAccountCreated(email: string): Promise<boolean> {
        return await this.updateUser(email, { HAS_ACCOUNT: true });
    }

    /**
     * Update ENTERED to TRUE for a user
     * @param {string} email - User's email
     * @returns {Promise<boolean>} Success status
     */
    async markEntryCompleted(email: string): Promise<boolean> {
        return await this.updateUser(email, { ENTERED: true });
    }

    /**
     * Mark a user as verified
     * @param {string} email - User's email
     * @returns {Promise<boolean>} Success status
     */
    async markAsVerified(email: string): Promise<boolean> {
        try {
            const userIndex: number = this.data.findIndex(user => user.EMAIL === email);
            if (userIndex === -1) {
                console.error(`User with email ${email} not found`);
                return false;
            }

            this.data[userIndex].VERIFIED = 'TRUE';
            await this.writeCsvData();
            //console.log(`User ${email} marked as verified`);
            return true;
        } catch (error: any) {
            console.error(`Error marking user as verified: ${error.message}`);
            return false;
        }
    }
    async flagOtpIssues(email: string): Promise<boolean> {
        return await this.updateUser(email, { OTP_ISSUE: true });
    }

    /**
     * Save current data to CSV file
     * @returns {Promise<void>}
     */
    async writeCsvData(): Promise<void> {
        try {
            if (this.data.length === 0) {
                throw new Error('No data to save');
            }

            // Get headers from the first user object
            const headers = Object.keys(this.data[0]);
            
            // Create CSV content
            const csvLines = [
                headers.join(','), // Header row
                ...this.data.map(user => 
                    headers.map(header => {
                        const value = (user as any)[header];
                        // Convert boolean values back to strings for CSV
                        if (typeof value === 'boolean') {
                            return value ? 'TRUE' : 'FALSE';
                        }
                        // Handle undefined/null values
                        if (value === undefined || value === null) {
                            return '';
                        }
                        return value;
                    }).join(',')
                )
            ];

            const csvContent = csvLines.join('\n');
            
            // Write to file
            fs.writeFileSync(this.csvFilePath, csvContent, 'utf8');
            //console.log(`CSV file saved successfully: ${this.csvFilePath}`);

        } catch (error: any) {
            console.error('Error saving CSV file:', error.message);
            throw error;
        }
    }

}

export default CsvHelper;