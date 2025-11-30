// Types and interfaces
interface Page {
    waitForSelector(selector: string, options?: any): Promise<any>;
    $(selector: string): Promise<any>;
    locator(selector: string): any;
    mouse: any;
    waitForTimeout(ms: number): Promise<void>;
    reload(options?: any): Promise<void>;
    url(): string;
    evaluate(fn: Function, ...args: any[]): Promise<any>;
    waitForLoadState(state: string, options?: any): Promise<void>;
    textContent(selector: string): Promise<string>;
}

interface Element {
    boundingBox(): Promise<any>;
    scrollIntoViewIfNeeded(): Promise<void>;
    click(): Promise<void>;
    hover(): Promise<void>;
    selectText(): Promise<void>;
    press(key: string): Promise<void>;
    type(text: string, options?: any): Promise<void>;
    dispatchEvent(event: string): Promise<void>;
    inputValue(): Promise<string>;
    isVisible(options?: any): Promise<boolean>;
    isEnabled(options?: any): Promise<boolean>;
    count(): Promise<number>;
    first(): Element;
    all(): Promise<Element[]>;
    selectOption(value: string): Promise<void>;
}

interface Locator {
    first(): Element;
    count(): Promise<number>;
    isVisible(options?: any): Promise<boolean>;
}

interface MousePosition {
    x: number;
    y: number;
}

/**
 * Browser Helper - Utility functions for browser automation
 * Contains reusable functions for mouse movement, clicking, form filling, etc.
 */
class BrowserHelper {
    private page: Page;
    private taskNumber: number | null = null;

    constructor(page: Page) {
        this.page = page;
        this.taskNumber = null;
    }

    /**
     * Set task number for logging
     * @param {number} taskNumber - Task number
     */
    setTaskNumber(taskNumber: number): void {
        this.taskNumber = taskNumber;
    }

    /**
     * Log message with task number prefix
     * @param {string} message - Message to log
     * @param {string} level - Log level (log, error, warn)
     */
    log(message: string, level: string = 'log'): void {
        try {
            const taskPrefix: string = this.taskNumber ? `[TASK-${this.taskNumber}]` : '[TASK-?]';
            const fullMessage: string = `${taskPrefix} ${message}`;
            
            switch (level) {
                case 'error':
                    console.error(fullMessage);
                    break;
                case 'warn':
                    console.warn(fullMessage);
                    break;
                default:
                    console.log(fullMessage);
                    break;
            }
        } catch (error: any) {
            // Fallback to simple console.log if there's any error
            console.log(`[TASK-?] ${message}`);
        }
    }

    /**
     * Generate random delay between min and max milliseconds
     * @param {number} min - Minimum delay in ms
     * @param {number} max - Maximum delay in ms
     * @returns {number} Random delay
     */
    randomDelay(min: number = 2500, max: number = 7000): number {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    /**
     * Move mouse realistically with Bezier curve
     */
    async moveMouseRealistically(targetX: number, targetY: number): Promise<void> {
        try {
            // Get the main page context for mouse operations (frames don't have mouse)
            const mainPage: Page = (this.page as any).originalPage || this.page;
            
            // Get current mouse position (or start from a random position)
            const startX: number = Math.random() * 200 + 100;
            const startY: number = Math.random() * 200 + 100;
            
            // Generate control points for Bezier curve
            const cp1X: number = startX + (targetX - startX) * 0.3 + (Math.random() - 0.5) * 200;
            const cp1Y: number = startY + (targetY - startY) * 0.3 + (Math.random() - 0.5) * 200;
            const cp2X: number = startX + (targetX - startX) * 0.7 + (Math.random() - 0.5) * 200;
            const cp2Y: number = startY + (targetY - startY) * 0.7 + (Math.random() - 0.5) * 200;
            
            // Number of steps for smooth movement
            const steps: number = Math.floor(Math.random() * 20) + 20; // 20-40 steps
            
            for (let i = 0; i <= steps; i++) {
                const t: number = i / steps;
                
                // Cubic Bezier curve calculation
                const x: number = Math.pow(1-t, 3) * startX + 
                             3 * Math.pow(1-t, 2) * t * cp1X + 
                             3 * (1-t) * Math.pow(t, 2) * cp2X + 
                             Math.pow(t, 3) * targetX;
                             
                const y: number = Math.pow(1-t, 3) * startY + 
                             3 * Math.pow(1-t, 2) * t * cp1Y + 
                             3 * (1-t) * Math.pow(t, 2) * cp2Y + 
                             Math.pow(t, 3) * targetY;
                
                await mainPage.mouse.move(x, y);
                
                // Variable speed - slower at start and end, faster in middle
                const speed: number = Math.sin(t * Math.PI) * 30 + 10;
                await this.page.waitForTimeout(Math.floor(speed));
            }
        } catch (error: any) {
            this.log(`⚠️ Mouse movement error: ${error.message}`);
            // Fallback to simple movement
            await this.page.mouse.move(targetX, targetY, { steps: 10 });
        }
    }

    /**
     * Simulate human-like click with proper event sequence
     * @param {string} selector - CSS selector to click
     * @param {Object} options - Click options
     */
    async humanClick(selector: string, options: any = {}): Promise<void> {
        try {
            this.log(`🎯 Looking for element: ${selector}`);
            
            // Wait for element to be visible and stable
            await this.page.waitForSelector(selector, { 
                state: 'visible',
                timeout: 7500 
            });
            
            // Get element bounding box
            const element: Element = await this.page.$(selector);
            if (!element) {
                throw new Error(`Element not found: ${selector}`);
            }

            const box: any = await element.boundingBox();
            if (!box) {
                throw new Error(`Element not visible: ${selector}`);
            }

            // Calculate click position (center of element with slight randomness)
            const clickX: number = box.x + box.width / 2 + (Math.random() - 0.5) * 10;
            const clickY: number = box.y + box.height / 2 + (Math.random() - 0.5) * 10;

            this.log(`📍 Clicking at position: (${Math.round(clickX)}, ${Math.round(clickY)})`);

            // Get current mouse position
            const currentPos: MousePosition = { x: 100, y: 100 }; // Start from a reasonable position

            // Move mouse to element with human-like movement
            await this.humanMouseMove(currentPos, { x: clickX, y: clickY });

            // Hover over element briefly (human behavior)
            await this.page.waitForTimeout(this.randomDelay(200, 500));

            // Scroll element into view if needed
            await element.scrollIntoViewIfNeeded();

            // Move mouse to element with realistic Bezier curve movement
            await this.moveMouseRealistically(clickX, clickY);
            
            // Hover for a moment (realistic behavior)
            await this.page.waitForTimeout(this.randomDelay(200, 800));
            
            // Mouse down and up with slight delay (realistic click)
            await this.page.mouse.down();
            await this.page.waitForTimeout(this.randomDelay(50, 150));
            await this.page.mouse.up();

            this.log(`Successfully clicked: ${selector}`);
            
            // Wait after click (human behavior)
            await this.page.waitForTimeout(this.randomDelay(300, 800));

        } catch (error: any) {
            console.error(`❌ Error clicking ${selector}:`, error.message);
            throw error;
        }
    }

    /**
     * Simulate human-like mouse movement with bezier curves
     * @param {MousePosition} from - Starting position {x, y}
     * @param {MousePosition} to - Target position {x, y}
     */
    async humanMouseMove(from: MousePosition, to: MousePosition): Promise<void> {
        try {
            // Create a bezier curve path for more human-like movement
            const steps: number = 20 + Math.floor(Math.random() * 10); // 20-30 steps
            const control1: MousePosition = {
                x: from.x + (to.x - from.x) * 0.3 + (Math.random() - 0.5) * 50,
                y: from.y + (to.y - from.y) * 0.3 + (Math.random() - 0.5) * 50
            };
            const control2: MousePosition = {
                x: from.x + (to.x - from.x) * 0.7 + (Math.random() - 0.5) * 50,
                y: from.y + (to.y - from.y) * 0.7 + (Math.random() - 0.5) * 50
            };

            for (let i = 0; i <= steps; i++) {
                const t: number = i / steps;
                const x: number = Math.pow(1 - t, 3) * from.x + 
                             3 * Math.pow(1 - t, 2) * t * control1.x + 
                             3 * (1 - t) * Math.pow(t, 2) * control2.x + 
                             Math.pow(t, 3) * to.x;
                const y: number = Math.pow(1 - t, 3) * from.y + 
                             3 * Math.pow(1 - t, 2) * t * control1.y + 
                             3 * (1 - t) * Math.pow(t, 2) * control2.y + 
                             Math.pow(t, 3) * to.y;

                await this.page.mouse.move(x, y);
                await this.page.waitForTimeout(10 + Math.random() * 20);
            }
        } catch (error: any) {
            console.error('❌ Error in mouse movement:', error.message);
        }
    }

    /**
     * Universal element waiter - waits up to 60 seconds for any element
     * @param {string} selector - CSS selector to wait for
     * @param {string} elementName - Name for logging
     * @param {any} context - Page or frame context to use
     * @returns {boolean} - True if found, false if timeout
     */
    async waitForElementRobust(selector: string, elementName: string = 'element', context: any = null): Promise<boolean | string> {
        try {
            this.log(`Waiting for ${elementName} (up to 60 seconds)...`);
            
            const pageContext: any = context || this.page;
            const maxAttempts: number = 160; // 60 seconds
            let attempts: number = 0;
            
            while (attempts < maxAttempts) {
                attempts++;
                
                if (attempts % 10 === 0) { // Log every 10 seconds
                    this.log(`Still waiting for ${elementName}... (${attempts}/160 seconds)`);
                }
                

                const isCaptchaBlocked: boolean = await this.checkForCaptchaBlock();
                if (isCaptchaBlocked) {
                    this.log(`🤖 CAPTCHA/DataDome block detected while waiting for ${elementName} - proxy/IP is blocked`);
                    throw new Error('CAPTCHA_BLOCKED');
                }

                // Reload page at 90 seconds to help with slow loading
                if (attempts === 90) {
                    this.log(`90 seconds reached - reloading page to help with slow loading...`);
                    try {
                        await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                        this.log(`Page reloaded successfully`);
                        
                        // Check if we're back on the main FIFA page after reload
                        const currentUrl: string = this.page.url();
                        if (currentUrl.includes('fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications')) {
                            this.log('Detected return to main FIFA page after reload - restarting flow from Enter Draw button');
                            // Wait a moment for page to fully load
                            await this.page.waitForTimeout(2000);
                            // This will be handled by the calling method
                            return 'RESTART_DRAW_ENTRY';
                        }
                    } catch (reloadError: any) {
                        this.log(`⚠️ Page reload failed: ${reloadError.message}, continuing...`);
                    }
                }
                
                try {
                    // Check for CAPTCHA block first before checking for elements
                    const captchaElement: boolean = await pageContext.locator('.captcha__footer').isVisible({ timeout: 500 });
                    if (captchaElement) {
                        this.log(`🤖 CAPTCHA detected while waiting for ${elementName} - proxy/IP is blocked`);
                        throw new Error('CAPTCHA_BLOCKED');
                    }
                    
                    const element: Element = pageContext.locator(selector).first();
                    const count: number = await pageContext.locator(selector).count();
                    
                    // Debug for terms checkbox specifically
                    if (elementName.includes('Terms checkbox') && attempts % 10 === 0) {
                        this.log(`🔍 Debug - Selector "${selector}": count=${count}`);
                        if (count > 0) {
                            const isVisible: boolean = await element.isVisible({ timeout: 1000 });
                            const isEnabled: boolean = await element.isEnabled({ timeout: 1000 });
                            this.log(`🔍 Debug - Element visible: ${isVisible}, enabled: ${isEnabled}`);
                        }
                    }
                    
                    if (await element.isVisible({ timeout: 1000 })) {
                        // For buttons, also check if they're clickable
                        if (selector.includes('button') || selector.includes('Apply') || selector.includes('Enter Draw')) {
                            const isClickable: boolean = await element.isEnabled({ timeout: 1000 });
                            if (isClickable) {
                                this.log(`Found clickable ${elementName} after ${attempts} seconds`);
                                return true;
                            } else {
                                this.log(`${elementName} is visible but not clickable yet... (${attempts}/160 seconds)`);
                            }
                        } else {
                            this.log(`Found ${elementName} after ${attempts} seconds`);
                            return true;
                        }
                    }
                } catch (error: any) {
                    // Check for specific network errors that require page refresh
                    if (error.message.includes('ERR_EMPTY_RESPONSE') || 
                        error.message.includes('ERR_CONNECTION_CLOSED') ||
                        error.message.includes('ERR_TIMED_OUT') ||
                        error.message.includes('net::ERR_') ||
                        error.message.includes('Navigation timeout') ||
                        error.message.includes('Protocol error') ||
                        error.message.includes('Target closed') ||
                        error.message.includes('Execution context was destroyed')) {
                        
                        this.log(`Network error detected: ${error.message} - refreshing page...`);
                        try {
                            await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                            await this.page.waitForTimeout(3000);
                            
                            // Check if we're back on the main FIFA page after reload
                            const currentUrl: string = this.page.url();
                            if (currentUrl.includes('fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/tickets')) {
                                this.log('Detected return to main FIFA page after reload - restarting flow from Enter Draw button');
                                await this.page.waitForTimeout(2000);
                                return 'RESTART_DRAW_ENTRY';
                            }
                            
                            // Reset attempt counter after successful reload
                            attempts = 0;
                            continue;
                        } catch (reloadError: any) {
                            this.log(`⚠️ Page reload failed: ${reloadError.message}, continuing...`);
                        }
                    }
                    // Continue waiting, proxy might be slow
                }
                
                // Use setTimeout instead of page.waitForTimeout for iframe compatibility
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            this.log(`❌ ${elementName} not found after 160 seconds - proxy may be blocked or too slow`);
            // Throw a specific timeout error that can trigger proxy retry
            throw new Error(`PROXY_TIMEOUT: ${elementName} not found after 160 seconds - proxy may be blocked or too slow`);
            
        } catch (error: any) {
            console.error(`❌ Error waiting for ${elementName}:`, error.message);
            
            // If it's our PROXY_TIMEOUT error, re-throw it to trigger proxy retry
            if (error.message.includes('PROXY_TIMEOUT')) {
                throw error;
            }
            
            return false;
        }
    }

    /**
     * Robust click that waits up to 60 seconds for element with retry logic
     * @param {string} selector - CSS selector to click
     * @param {string} elementName - Name for logging
     * @param {any} context - Page or frame context to use
     * @param {number} maxRetries - Maximum number of retries (default: 2)
     * @returns {boolean} - True if clicked, false if timeout
     */
    async robustClick(selector: string, elementName: string = 'element', context: any = null, maxRetries: number = 2): Promise<boolean | string> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`🎯 Attempt ${attempt}/${maxRetries} - Robust clicking ${elementName}...`);
                
                const pageContext: any = context || this.page;
                
                // Wait for element with 60-second timeout
                const found: boolean | string = await this.waitForElementRobust(selector, elementName, pageContext);

                if(found === 'RESTART_DRAW_ENTRY'){
                    return 'RESTART_DRAW_ENTRY';
                }

                if (!found) {
                    this.log(`❌ ${elementName} not found on attempt ${attempt}`);
                    if (attempt === maxRetries) {
                        return false;
                    }
                    continue;
                }
                
                // Click with realistic movement (within context)
                await this.humanClickInContext(selector, pageContext);
                this.log(`Successfully clicked ${elementName} on attempt ${attempt}`);
                return true;
                
            } catch (error: any) {
                console.error(`❌ Error clicking ${elementName} on attempt ${attempt}:`, error.message);
                
                // If it's a proxy timeout, re-throw to trigger proxy retry
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error;
                }
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to click ${elementName} after ${maxRetries} attempts`);
                    return false;
                }
                
                // Wait before retry
                this.log(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Robust form fill that waits up to 60 seconds for field with retry logic
     * @param {string} selector - CSS selector for field
     * @param {string} value - Value to fill
     * @param {string} fieldName - Name for logging
     * @param {any} context - Page or frame context to use
     * @param {number} maxRetries - Maximum number of retries (default: 2)
     * @returns {boolean} - True if filled, false if timeout
     */
    async robustFill(selector: string, value: string, fieldName: string = 'field', context: any = null, maxRetries: number = 2): Promise<boolean> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`📝 Attempt ${attempt}/${maxRetries} - Robust filling ${fieldName}...`);
                
                const pageContext: any = context || this.page;
                
                // Wait for field with 60-second timeout
                const found: boolean | string = await this.waitForElementRobust(selector, fieldName, pageContext);
                if (!found) {
                    this.log(`❌ ${fieldName} not found on attempt ${attempt}`);
                    if (attempt === maxRetries) {
                        return false;
                    }
                    continue;
                }
                
                const field: Element = pageContext.locator(selector).first();
                
                // Click field realistically
                await this.humanClickInContext(selector, pageContext);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 400)));
                
                // Clear field completely
                await field.selectText();
                await field.press('Delete');
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 400)));
                
                // Type with realistic delays
                for (let i = 0; i < value.length; i++) {
                    const char: string = value[i];
                    await field.type(char, { delay: this.randomDelay(80, 200) });
                    
                    // Occasional pause
                    if (Math.random() < 0.1) {
                        await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 500)));
                    }
                }
                
                // Trigger events
                await field.dispatchEvent('input');
                await field.dispatchEvent('change');
                await field.dispatchEvent('blur');
                
                this.log(`${fieldName} filled successfully on attempt ${attempt}: ${value}`);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                return true;
                
            } catch (error: any) {
                console.error(`❌ Error filling ${fieldName} on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to fill ${fieldName} after ${maxRetries} attempts`);
                    return false;
                }
                
                // Wait before retry
                this.log(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Robust dropdown selection that waits up to 60 seconds with realistic clicking and retry logic
     * @param {string} selector - CSS selector for dropdown
     * @param {string} value - Value to select
     * @param {string} fieldName - Name for logging
     * @param {any} context - Page or frame context to use
     * @param {number} maxRetries - Maximum number of retries (default: 2)
     * @returns {boolean} - True if selected, false if timeout
     */
    async robustSelect(selector: string, value: string, fieldName: string = 'dropdown', context: any = null, maxRetries: number = 2): Promise<boolean> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                this.log(`📋 Attempt ${attempt}/${maxRetries} - Robust selecting ${fieldName}...`);
                
                const pageContext: any = context || this.page;
                
                // Wait for dropdown with 60-second timeout
                const found: boolean | string = await this.waitForElementRobust(selector, fieldName, pageContext);
                if (!found) {
                    this.log(`❌ ${fieldName} not found on attempt ${attempt}`);
                    if (attempt === maxRetries) {
                        return false;
                    }
                    continue;
                }
                
                const dropdown: Element = pageContext.locator(selector).first();
                
                // Click dropdown realistically to open it
                await this.humanClickInContext(selector, pageContext);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(500, 1000)));
                
                // Try realistic option clicking first
                try {
                    this.log(`🎯 Looking for option with value: ${value}`);
                    const optionSelector: string = `${selector} option[value="${value}"]`;
                    const option: Element = pageContext.locator(optionSelector);
                    
                    if (await option.isVisible({ timeout: 3000 })) {
                        this.log(`Found option, clicking realistically...`);
                        await this.humanClickInContext(optionSelector, pageContext);
                        this.log(`${fieldName} selected realistically on attempt ${attempt}: ${value}`);
                        await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                        return true;
                    }
                } catch (error: any) {
                    this.log(`⚠️ Realistic option clicking failed, using programmatic selection...`);
                }
                
                // Fallback to programmatic selection
                await dropdown.selectOption(value);
                
                // Trigger events
                await dropdown.dispatchEvent('change');
                await dropdown.dispatchEvent('blur');
                
                this.log(`${fieldName} selected (programmatic) on attempt ${attempt}: ${value}`);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                return true;
                
            } catch (error: any) {
                console.error(`❌ Error selecting ${fieldName} on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    this.log(`❌ Failed to select ${fieldName} after ${maxRetries} attempts`);
                    return false;
                }
                
                // Wait before retry
                this.log(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Human-like click within specific context (page or frame)
     * @param {string} selector - CSS selector to click
     * @param {any} context - Page or frame context
     */
    async humanClickInContext(selector: string, context: any): Promise<void> {
        try {
            this.log(`🎯 Human clicking in context: ${selector}`);
            
            const element: Element = context.locator(selector).first();
            if (!(await element.isVisible({ timeout: 5000 }))) {
                throw new Error(`Element not visible: ${selector}`);
            }

            // Scroll element into view if needed
            await element.scrollIntoViewIfNeeded();
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 500)));

            // For iframe, use simple element click (no mouse coordination)
            if (context !== this.page) {
                this.log(`📍 Using simple click for iframe element`);
                this.log(`📍 Context type: ${context.constructor.name}`);
                this.log(`📍 Page type: ${this.page.constructor.name}`);
                
                // Just click the element directly - no mouse movement
                await element.click();
                
                this.log(`Successfully clicked iframe element: ${selector}`);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 800)));
                return;
            }

            // For main page, use normal realistic mouse movement
            const box: any = await element.boundingBox();
            if (!box) {
                throw new Error(`Element not visible: ${selector}`);
            }

            // Calculate click position (center area with randomness)
            const clickX: number = box.x + box.width * (0.3 + Math.random() * 0.4);
            const clickY: number = box.y + box.height * (0.3 + Math.random() * 0.4);

            this.log(`📍 Clicking at position: (${Math.round(clickX)}, ${Math.round(clickY)})`);

            // Move mouse to element with realistic movement
            await this.moveMouseRealistically(clickX, clickY);
            
            // Hover for a moment
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 800)));
            
            // Click with mouse down/up
            await this.page.mouse.down();
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(50, 150)));
            await this.page.mouse.up();
            
            this.log(`Successfully clicked in context: ${selector}`);
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(100, 300)));
            
        } catch (error: any) {
            console.error(`❌ Failed to click in context ${selector}:`, error.message);
            throw error;
        }
    }

    /**
     * Simulate human-like scrolling
     * @param {number} distance - Scroll distance (positive = down, negative = up)
     * @param {number} steps - Number of scroll steps
     */
    async humanScroll(distance: number, steps: number = 5): Promise<void> {
        const stepDistance: number = distance / steps;
        
        for (let i = 0; i < steps; i++) {
            await this.page.mouse.wheel(0, stepDistance);
            await this.page.waitForTimeout(this.randomDelay(100, 300));
        }
    }

    /**
     * Wait for page to be fully loaded with human-like behavior
     */
    async waitForPageLoad(): Promise<void> {
        this.log('Waiting for page to load...');
        
        try {
            // Wait for network to be idle
            await this.page.waitForLoadState('networkidle', { timeout: 30000 });
            
            // Additional random wait (human behavior)
            await this.page.waitForTimeout(this.randomDelay(500, 750));
            
            this.log('Page loaded successfully');
        } catch (error: any) {
            // Check for specific network errors that require page refresh
            if (error.message.includes('ERR_EMPTY_RESPONSE') || 
                error.message.includes('ERR_CONNECTION_CLOSED') ||
                error.message.includes('ERR_TIMED_OUT') ||
                error.message.includes('net::ERR_') ||
                error.message.includes('Navigation timeout') ||
                error.message.includes('Protocol error') ||
                error.message.includes('Target closed') ||
                error.message.includes('Execution context was destroyed')) {
                
                this.log(`Network error detected during page load: ${error.message} - refreshing page...`);
                try {
                    await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                    await this.page.waitForTimeout(3000);
                    this.log('Page refreshed successfully after network error');
                } catch (reloadError: any) {
                    this.log(`⚠️ Page refresh failed: ${reloadError.message}, continuing...`);
                }
            } else {
                this.log(`⚠️ Page load warning: ${error.message}, continuing...`);
            }
        }
    }

    /**
     * Fill a field with realistic typing behavior
     */
    async fillFieldRealistically(selector: string, value: string, fieldName: string): Promise<void> {
        try {
            this.log(`📝 Filling ${fieldName}...`);
            
            const field: Element = this.page.locator(selector).first();
            
            // Click and focus on field with realistic movement
            await this.humanClick(selector);
            await this.page.waitForTimeout(this.randomDelay(200, 400));
            
            // Clear field completely
            await field.selectText();
            await field.press('Delete');
            await this.page.waitForTimeout(this.randomDelay(200, 400));
            
            // Type character by character with realistic delays
            for (let i = 0; i < value.length; i++) {
                const char: string = value[i];
                await field.type(char, { delay: this.randomDelay(50, 150) });
                
                // Occasional longer pause (like human thinking)
                if (Math.random() < 0.1) { // 10% chance
                    await this.page.waitForTimeout(this.randomDelay(200, 500));
                }
            }
            
            // Trigger events to ensure form validation
            await field.dispatchEvent('input');
            await field.dispatchEvent('change');
            await field.dispatchEvent('blur');
            
            // Verify the value was filled correctly
            const filledValue: string = await field.inputValue();
            this.log(`${fieldName} filled: ${filledValue}`);
            
            // Small pause after filling
            await this.page.waitForTimeout(this.randomDelay(300, 600));
            
        } catch (error: any) {
            this.log(`⚠️ Error filling ${fieldName}: ${error.message}`);
        }
    }

    /**
     * Wait for redirect or detect blocked account
     * @param {string} initialUrl - URL before action
     * @param {number} timeoutMs - Timeout in milliseconds
     * @param {string} actionName - Name of the action for logging
     * @returns {string} 'REDIRECTED' or 'BLOCKED'
     */
    async waitForRedirectOrDetectBlock(initialUrl: string, timeoutMs: number = 30000, actionName: string = 'action'): Promise<string> {
        try {
            const startTime: number = Date.now();
            const endTime: number = startTime + timeoutMs;
            
            while (Date.now() < endTime) {
                const currentUrl: string = this.page.url();
                
                // Check if URL changed (redirect happened)
                if (currentUrl !== initialUrl) {
                    this.log(`Redirect detected after ${actionName} - URL changed to: ${currentUrl}`);
                    return 'REDIRECTED';
                }
                
                // Check for email verification page elements every few seconds (not blocked, just waiting for email)
                const elapsed2: number = Date.now() - startTime;
                
                // Check for email verification every 3 seconds
                if (elapsed2 % 3000 < 1000) {
                    try {
                        this.log(`🔍 Checking for email verification elements... (${Math.round(elapsed2/1000)}s)`);
                        
                        // Use multiple detection methods for email verification
                        
                        // Method 1: Check for OTP input field
                        const otpInputExists: boolean = await this.page.locator('input[name="otp"]').isVisible({ timeout: 500 }).catch(() => false);
                        if (otpInputExists) {
                            this.log(`📧 Email verification page detected after ${actionName} - found OTP input field`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 2: Check for "Enter Code" placeholder
                        const enterCodeExists: boolean = await this.page.locator('input[placeholder="Enter Code"]').isVisible({ timeout: 500 }).catch(() => false);
                        if (enterCodeExists) {
                            this.log(`📧 Email verification page detected after ${actionName} - found Enter Code field`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 3: Check for "Verify My Code" button
                        const verifyButtonExists: boolean = await this.page.locator('button[id="auto-submit"]').isVisible({ timeout: 500 }).catch(() => false);
                        if (verifyButtonExists) {
                            this.log(`📧 Email verification page detected after ${actionName} - found Verify My Code button`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 4: Check for "Check your email" heading
                        const checkEmailHeading: boolean = await this.page.locator('h1:has-text("Check your email")').isVisible({ timeout: 500 }).catch(() => false);
                        if (checkEmailHeading) {
                            this.log(`📧 Email verification page detected after ${actionName} - found Check your email heading`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 5: Check for verification container
                        const verifyContainer: boolean = await this.page.locator('.verify-content-form-container').isVisible({ timeout: 500 }).catch(() => false);
                        if (verifyContainer) {
                            this.log(`📧 Email verification page detected after ${actionName} - found verification container`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                        // Method 6: Check page text content
                        const pageText: string = await this.page.textContent('body').catch(() => '');
                        if (pageText.includes('Check your email') || 
                            pageText.includes('Enter Code') ||
                            pageText.includes('Verify My Code') ||
                            pageText.includes('one click away from completing')) {
                            this.log(`📧 Email verification page detected after ${actionName} - found verification text`);
                            return 'EMAIL_VERIFICATION';
                        }
                        
                    } catch (evalError: any) {
                        this.log(`⚠️ Error checking for email verification: ${evalError.message}`);
                    }
                }
                
                // Check for error messages that indicate issues
                try {
                    const hasError: boolean = await this.page.evaluate(() => {
                        const errorElements = document.querySelectorAll('.error, .alert-danger, .invalid-feedback, .inputErrorMsg');
                        return errorElements.length > 0;
                    });
                    
                    if (hasError) {
                        this.log(`⚠️ Error message detected after ${actionName} - not blocked, just error`);
                        return 'ERROR';
                    }
                } catch (evalError: any) {
                    // Continue waiting
                }
                
                // Log progress every 10 seconds
                const elapsed: number = Date.now() - startTime;
                if (elapsed % 10000 < 1000) { // Roughly every 10 seconds
                    this.log(`Still waiting for redirect after ${actionName}... (${Math.round(elapsed/1000)}/${Math.round(timeoutMs/1000)}s)`);
                }
                
                await this.page.waitForTimeout(1000); // Wait 1 second before next check
            }
            
            // If we reach here, no redirect happened within timeout
            this.log(`🚫 No redirect after ${actionName} for ${Math.round(timeoutMs/1000)}s - account/proxy appears to be blocked`);
            return 'BLOCKED';
            
        } catch (error: any) {
            this.log(`⚠️ Error during redirect detection: ${error.message}`);
            return 'ERROR';
        }
    }

    /**
     * Check for CAPTCHA block
     */
    async checkForCaptchaBlock(): Promise<boolean> {
        // check if .captcha__footer is in the page then we are blocked
        const captchaElement: boolean = await this.page.locator('.captcha__footer').isVisible();
        if (captchaElement) {
            this.log('❌ Captcha block detected');
            return true;
        }
        return false;
    }
}

export default BrowserHelper;
