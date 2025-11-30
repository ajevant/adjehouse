import { path } from "ghost-cursor";

/**
 * Human-like interaction helpers for browser automation
 * Provides realistic mouse movements, clicks, scrolling, and element waiting
 */
class HumanInteractions {
    public page: any;
    private originalPage: any; // Store reference for mouse operations in iframes
    private lastMousePosition: { x: number; y: number }; // Track last mouse position
    private lastActionTime: number; // Track time of last action for realistic pacing

    constructor(page: any) {
        this.page = page;
        this.originalPage = page; // Store reference for mouse operations in iframes
        this.lastMousePosition = { x: 100, y: 100 }; // Track last mouse position
        this.lastActionTime = Date.now();
    }

    /**
     * Update the page reference (useful when switching between pages/contexts)
     * @param {Object} page - Playwright page object
     */
    setPage(page: any): void {
        this.page = page;
        if (!this.originalPage) {
            this.originalPage = page;
        }
    }

    getPageUrl(): string {
        if(!this.page){
            return 'page not initialized';
        }
        return this.page?.url() || 'page not initialized';
    }
    /**
     * Perform random idle mouse movements (simulates human reading/thinking)
     * @param {number} duration - Duration in ms for idle movements
     */
    async randomIdleMovements(duration: number = 2000): Promise<void> {
        try {
            const movements = 2 + Math.floor(Math.random() * 3); // 2-4 small movements
            const interval = duration / movements;
            
            for (let i = 0; i < movements; i++) {
                const currentPos = this.lastMousePosition;
                const randomOffset = {
                    x: currentPos.x + (Math.random() - 0.5) * 100, // Small random movements
                    y: currentPos.y + (Math.random() - 0.5) * 100
                };
                
                await this.humanMouseMove(currentPos, randomOffset);
                this.lastMousePosition = randomOffset;
                
                if (i < movements - 1) {
                    await this.page.waitForTimeout(interval + Math.random() * 500);
                }
            }
        } catch (error: any) {
            // Silently continue
        }
    }

    /**
     * Simulate reading behavior - move eyes/mouse across text
     * @param {string} selector - Element to "read"
     * @param {number} readingTime - How long to simulate reading (ms)
     */
    async simulateReading(selector: string, readingTime: number = 3000): Promise<void> {
        try {
            const element = await this.page.$(selector);
            if (!element) return;

            const box = await element.boundingBox();
            if (!box) return;

            // Simulate eye movements across the text
            const numMovements = 3 + Math.floor(Math.random() * 4); // 3-6 movements
            const timePerMovement = readingTime / numMovements;

            for (let i = 0; i < numMovements; i++) {
                // Random position within the element (simulating reading different parts)
                const targetX = box.x + Math.random() * box.width;
                const targetY = box.y + Math.random() * box.height;

                await this.humanMouseMove(this.lastMousePosition, { x: targetX, y: targetY });
                this.lastMousePosition = { x: targetX, y: targetY };
                
                await this.page.waitForTimeout(timePerMovement + Math.random() * 500);
            }
        } catch (error: any) {
            // Silently continue
        }
    }

    /**
     * Scroll to element smoothly before interacting
     * @param {string} selector - Element to scroll to
     */
    async smoothScrollToElement(selector: string): Promise<void> {
        try {
            const element = await this.page.$(selector);
            if (!element) return;

            const box = await element.boundingBox();
            if (!box) return;

            // Scroll in multiple steps for smooth, human-like scrolling
            const targetY = box.y + box.height / 2;
            const currentScroll = await this.page.evaluate(() => window.scrollY);
            const scrollDistance = targetY - currentScroll - (window.innerHeight / 2);
            
            if (Math.abs(scrollDistance) > 100) {
                const steps = 5 + Math.floor(Math.random() * 3); // 5-7 scroll steps
                const stepSize = scrollDistance / steps;

                for (let i = 0; i < steps; i++) {
                    await this.page.evaluate((step) => {
                        window.scrollBy(0, step);
                    }, stepSize);
                    await this.page.waitForTimeout(50 + Math.random() * 100);
                }
            }
        } catch (error: any) {
            // Silently continue
        }
    }

    /**
     * Get current mouse position from the browser
     * @returns {Promise<Object>} Current mouse position {x, y}
     */
    async getCurrentMousePosition(): Promise<{ x: number; y: number }> {
        try {
            const position = await this.page.evaluate(() => {
                return {
                    x: (window as any).mouseX || 0,
                    y: (window as any).mouseY || 0
                };
            });
            return position;
        } catch (error) {
            // Fallback to last known position
            return this.lastMousePosition;
        }
    }

    /**
     * Generate random delay between min and max milliseconds
     * @param {number} min - Minimum delay in ms
     * @param {number} max - Maximum delay in ms
     * @returns {number} Random delay
     */
    randomDelay(min: number = 1000, max: number = 3000): number {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    /**
     * Simulate human-like mouse movement using ghost-cursor (realistic Bezier curves + Fitts's Law)
     * @param {Object} from - Starting position {x, y}
     * @param {Object} to - Target position {x, y}
     */
    async humanMouseMove(from: { x: number; y: number }, to: { x: number; y: number }): Promise<void> {
        try {
            // Use ghost-cursor to generate realistic path with timestamps
            const route = path(from, to, { useTimestamps: true }) as Array<{ x: number; y: number; timestamp: number }>;
            
            if (!route || route.length === 0) {
                // Fallback if path generation fails
                await this.page.mouse.move(to.x, to.y);
                this.lastMousePosition = to;
                return;
            }

            const startTime = Date.now();
            
            for (let i = 0; i < route.length; i++) {
                const point = route[i];
                const targetTime = startTime + (point.timestamp - route[0].timestamp);
                
                // Move to point
                await this.page.mouse.move(point.x, point.y);
                this.lastMousePosition = { x: point.x, y: point.y };
                
                // Wait for next point timing (respect ghost-cursor's timing)
                if (i < route.length - 1) {
                    const nextPoint = route[i + 1];
                    const delay = (nextPoint.timestamp - point.timestamp);
                    if (delay > 0) {
                        await new Promise(resolve => setTimeout(resolve, Math.max(1, delay)));
                    }
                }
            }
        } catch (error: any) {
            console.error('Error in mouse movement:', error.message);
            // Fallback to simple movement
            try {
                await this.page.mouse.move(to.x, to.y);
                this.lastMousePosition = to;
            } catch (fallbackError: any) {
                // Silently fail
            }
        }
    }

    /**
     * Simulate human-like click with proper event sequence
     * @param {string} selector - CSS selector to click
     * @param {Object} options - Click options
     */
    async humanClick(selector: string, options: any = {}): Promise<void> {
        try {
            
            // Wait for element to be visible and stable
            await this.page.waitForSelector(selector, { 
                state: 'visible',
                timeout: 7500 
            });
            
            // Get element bounding box
            const element = await this.page.$(selector);
            if (!element) {
                throw new Error(`Element not found: ${selector}`);
            }

            const box = await element.boundingBox();
            if (!box) {
                throw new Error(`Element not visible: ${selector}`);
            }

            // Calculate click position (avoid exact center; choose inner random band)
            const clickX = box.x + box.width * (0.25 + Math.random() * 0.5);
            const clickY = box.y + box.height * (0.25 + Math.random() * 0.5);

            // Use last known mouse position for more realistic movement
            const currentPos = this.lastMousePosition;

            // Ensure element in view and hover to fire pointerover/mouseover
            await element.scrollIntoViewIfNeeded();
            await element.hover({ position: { x: Math.max(1, Math.min(box.width - 1, clickX - box.x)), y: Math.max(1, Math.min(box.height - 1, clickY - box.y)) } });
            // Move mouse to element with realistic Bezier curve movement once
            await this.humanMouseMove(currentPos, { x: clickX, y: clickY });
            
            // Hover for a moment (realistic behavior)
            await this.page.waitForTimeout(this.randomDelay(120, 420));
            // Small micro-move on element to generate mousemove while hovering
            const microX = clickX + (Math.random() - 0.5) * Math.min(6, box.width * 0.05);
            const microY = clickY + (Math.random() - 0.5) * Math.min(6, box.height * 0.05);
            await this.page.mouse.move(microX, microY);
            await this.page.waitForTimeout(30 + Math.random() * 70);
            
            // Mouse down and up with slight delay (realistic click)
            await this.page.mouse.down();
            await this.page.waitForTimeout(this.randomDelay(50, 150));
            await this.page.mouse.up();

            // Update last mouse position
            this.lastMousePosition = { x: clickX, y: clickY };
            
            // Wait after click (human behavior)
            await this.page.waitForTimeout(this.randomDelay(300, 800));

        } catch (error: any) {
            console.error(`Error clicking ${selector}:`, error.message);
            throw error;
        }
    }

    /**
     * Universal element waiter - waits up to specified seconds for any element
     * @param {string} selector - CSS selector to wait for
     * @param {string} elementName - Name for logging
     * @param {Object} context - Page or frame context to use
     * @param {number} timeoutSeconds - Maximum time to wait in seconds (default: 60)
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean|string} - True if found, false if timeout, 'RESTART_DRAW_ENTRY' for special case
     */
    async waitForElementRobust(selector: string, elementName: string = 'element', context: any = null, timeoutSeconds: number = 60, logFunction: any = console.log): Promise<boolean | string> {
        try {
            
            const pageContext = context || this.page;
            const maxAttempts = timeoutSeconds;
            let attempts = 0;
            
            while (attempts < maxAttempts) {
                attempts++;


                if(selector === 'button[aria-label="My Account"]' || selector === 'a[href*="fifa-fwc26-us.tickets.fifa.com"]' || selector === 'a[label="Sign In"]'){
                    // click on accept cookie button
                    try{
                        const cookieElement = pageContext.locator('div[class="onetrust-pc-dark-filter ot-fade-in"]');
                        const count = await cookieElement.count();
                        if (count > 0) {
                            await cookieElement.evaluate(element => element.remove());
                        }
                    }catch(error: any){
                        // Silently continue - no logging to prevent console errors
                    }
                   
                }
                
                if (attempts % 10 === 0) { // Log every 10 seconds
                }
                
                // Reload page at 90 seconds to help with slow loading
                if (attempts === 90 && timeoutSeconds >= 90) {
                    try {
                        await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                        
                        // Check if we're back on the main FIFA page after reload
                        const currentUrl = this.page.url();
                        if (currentUrl.includes('fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications')) {
                            // Wait a moment for page to fully load
                            await this.page.waitForTimeout(2000);
                            return 'RESTART_DRAW_ENTRY';
                        }
                    } catch (reloadError) {
                    }
                }
                
                try {
                    // Check for browser error pages first using quick detection
                    if (await this.browser_detectErrorPageQuick()) {
                        try {
                            logFunction('Detected network error, reloading...')
                            await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                            await this.page.waitForTimeout(3000);
                        
                            // Reset attempt counter after successful reload
                            attempts = 0;
                            continue;
                        } catch (reloadError: any) {
                            logFunction(`Page reload failed after error page detection: ${reloadError.message}, continuing...`);
                        }
                    }
                    
                    const element = pageContext.locator(selector).first();
                    const count = await pageContext.locator(selector).count();
                    
                    // Debug for specific elements
                    if (elementName.includes('Terms checkbox') && attempts % 10 === 0) {
                        logFunction(`Debug - Selector "${selector}": count=${count}`);
                        if (count > 0) {
                            const isVisible = await element.isVisible({ timeout: 1000 });
                            const isEnabled = await element.isEnabled({ timeout: 1000 });
                            logFunction(`Debug - Element visible: ${isVisible}, enabled: ${isEnabled}`);
                        }
                    }
                    
                    if (await element.isVisible({ timeout: 1000 })) {
                        // For buttons, also check if they're clickable
                        if (selector.includes('button') || selector.includes('Apply') || selector.includes('Enter Draw')) {
                            const isClickable = await element.isEnabled({ timeout: 1000 });
                            if (isClickable) {
                                //logFunction(`Found clickable ${elementName} after ${attempts} seconds`);
                                return true;
                            } else {
                               //logFunction(`${elementName} is visible but not clickable yet... (${attempts}/${timeoutSeconds} seconds)`);
                            }
                        } else {
                           // logFunction(`Found ${elementName} after ${attempts} seconds`);
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
                        
                        logFunction(`Network error detected: ${error.message} - refreshing page...`);
                        try {
                            await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
                            await this.page.waitForTimeout(3000);
                            
                            // Check if we're back on the main FIFA page after reload
                            const currentUrl = this.page.url();
                            if (currentUrl.includes('fifa-fwc26-us.tickets.fifa.com/account/lotteryApplications')) {
                                logFunction('Detected return to main FIFA page after reload - restarting flow from Enter Draw button');
                                await this.page.waitForTimeout(2000);
                                return 'RESTART_DRAW_ENTRY';
                            }
                            
                            // Reset attempt counter after successful reload
                            attempts = 0;
                            continue;
                        } catch (reloadError:any) {
                            logFunction(`Page reload failed: ${reloadError.message}, continuing...`);
                        }
                    }
                    // Continue waiting, proxy might be slow
                }
                
                // Use setTimeout instead of page.waitForTimeout for iframe compatibility
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            // Throw a specific timeout error that can trigger proxy retry
            throw new Error(`PROXY_TIMEOUT: ${elementName} not found after ${timeoutSeconds} seconds - proxy may be blocked or too slow`);
            
        } catch (error: any) {
            logFunction(`Error waiting for ${elementName}: ${error.message}`);
            
            // If it's our PROXY_TIMEOUT error, re-throw it to trigger proxy retry
            if (error.message.includes('PROXY_TIMEOUT')) {
                throw error;
            }
            
            return false;
        }
    }

    /**
     * Human-like click within specific context (page or frame)
     * @param {string} selector - CSS selector to click
     * @param {Object} context - Page or frame context
     * @param {Function} logFunction - Optional logging function
     */
    async humanClickInContext(selector: string, context: any, logFunction: Function = console.log, fastMode: boolean = false): Promise<void> {
        try {
            const multiplier = fastMode ? 0.1 : 1;
            const element = context.locator(selector).first();
            if (!(await element.isVisible({ timeout: 5000 }))) {
                throw new Error(`Element not visible: ${selector}`);
            }

            // Smooth scroll to element before interaction
            await this.smoothScrollToElement(selector).catch(() => {});
            
            // Scroll element into view if needed
            await element.scrollIntoViewIfNeeded();
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 500) * multiplier));
            
            // Light hesitation behavior only (no exaggerated jitters)
            if (Math.random() < 0.2) {
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(150, 350) * multiplier));
            }

            // Compute a realistic click position within element
            const box = await element.boundingBox();
            if (!box) {
                throw new Error(`Element not visible: ${selector}`);
            }
            const clickX = box.x + box.width * (0.25 + Math.random() * 0.5);
            const clickY = box.y + box.height * (0.25 + Math.random() * 0.5);

            // If context has no mouse (frame/frameLocator), fall back to direct click
            const hasMouse = context && context.mouse && typeof context.mouse.down === 'function';
            if (!hasMouse) {
                await element.scrollIntoViewIfNeeded();
                await element.hover({ position: { x: Math.max(1, Math.min(box.width - 1, clickX - box.x)), y: Math.max(1, Math.min(box.height - 1, clickY - box.y)) } });
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(100, 220) * multiplier));
                await element.click();
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(120, 260) * multiplier));
                return;
            }

            // Hover to ensure pointerover/mouseover fire
            await element.hover({ position: { x: Math.max(1, Math.min(box.width - 1, clickX - box.x)), y: Math.max(1, Math.min(box.height - 1, clickY - box.y)) } });
            // Move mouse realistically towards click point (page or provided context)
            await this.moveMouseRealisticallyInContext(clickX, clickY, context);
            
            // Hover for a moment
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(120, 320) * multiplier));
            // Small on-element micro movement to create additional mousemove
            const microX = clickX + (Math.random() - 0.5) * Math.min(6, box.width * 0.05);
            const microY = clickY + (Math.random() - 0.5) * Math.min(6, box.height * 0.05);
            const pageToUseForMicro = context && context.mouse ? context : this.page;
            await pageToUseForMicro.mouse.move(microX, microY);
            await new Promise(resolve => setTimeout(resolve, 20 + Math.random() * 60));
            
            // Click with mouse down/up using the correct context
            const pageToUse = context || this.page;
            await pageToUse.mouse.down();
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(50, 150) * multiplier));
            await pageToUse.mouse.up();
            
            // Update last mouse position
            this.lastMousePosition = { x: clickX, y: clickY };
            
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(100, 300) * multiplier));
            
        } catch (error: any) {
            console.error(`Failed to click in context ${selector}:`, error.message);
            throw error;
        }
    }

    /**
     * Move mouse realistically using ghost-cursor (realistic Bezier curves + Fitts's Law)
     * @param {number} targetX - Target X coordinate
     * @param {number} targetY - Target Y coordinate
     */
    async moveMouseRealistically(targetX: number, targetY: number): Promise<void> {
        try {
            // Use last known mouse position for more realistic movement
            const from = { x: this.lastMousePosition.x, y: this.lastMousePosition.y };
            const to = { x: targetX, y: targetY };
            
            // Use ghost-cursor to generate realistic path with timestamps
            const route = path(from, to, { useTimestamps: true }) as Array<{ x: number; y: number; timestamp: number }>;
            
            if (!route || route.length === 0) {
                // Fallback if path generation fails
                await this.page.mouse.move(targetX, targetY);
                this.lastMousePosition = { x: targetX, y: targetY };
                return;
            }

            const startTime = Date.now();
            
            for (let i = 0; i < route.length; i++) {
                const point = route[i];
                const targetTime = startTime + (point.timestamp - route[0].timestamp);
                
                // Move to point
                await this.page.mouse.move(point.x, point.y);
                this.lastMousePosition = { x: point.x, y: point.y };
                
                // Wait for next point timing (respect ghost-cursor's timing)
                if (i < route.length - 1) {
                    const nextPoint = route[i + 1];
                    const delay = (nextPoint.timestamp - point.timestamp);
                    if (delay > 0) {
                        await new Promise(resolve => setTimeout(resolve, Math.max(1, delay)));
                    }
                }
            }
        } catch (error: any) {
            // Fallback to simple movement
            try {
                await this.page.mouse.move(targetX, targetY, { steps: 10 });
                this.lastMousePosition = { x: targetX, y: targetY };
            } catch (fallbackError: any) {
                // Silently fail
            }
        }
    }

    /**
     * Move mouse realistically using ghost-cursor (realistic Bezier curves + Fitts's Law)
     * Works with both page and iframe contexts
     * @param {number} targetX - Target X coordinate
     * @param {number} targetY - Target Y coordinate
     * @param {Object} context - Page or frame context to use
     */
    async moveMouseRealisticallyInContext(targetX: number, targetY: number, context: any = null): Promise<void> {
        try {
            // Use the provided context or fall back to main page
            const pageToUse = context || this.page;
            
            // Use last known mouse position for more realistic movement
            const from = { x: this.lastMousePosition.x, y: this.lastMousePosition.y };
            const to = { x: targetX, y: targetY };
            
            // Use ghost-cursor to generate realistic path with timestamps
            const route = path(from, to, { useTimestamps: true }) as Array<{ x: number; y: number; timestamp: number }>;
            
            if (!route || route.length === 0) {
                // Fallback if path generation fails
                await pageToUse.mouse.move(targetX, targetY);
                this.lastMousePosition = { x: targetX, y: targetY };
                return;
            }

            const startTime = Date.now();
            
            for (let i = 0; i < route.length; i++) {
                const point = route[i];
                const targetTime = startTime + (point.timestamp - route[0].timestamp);
                
                // Move to point using the correct context
                await pageToUse.mouse.move(point.x, point.y);
                this.lastMousePosition = { x: point.x, y: point.y };
                
                // Wait for next point timing (respect ghost-cursor's timing)
                if (i < route.length - 1) {
                    const nextPoint = route[i + 1];
                    const delay = (nextPoint.timestamp - point.timestamp);
                    if (delay > 0) {
                        await new Promise(resolve => setTimeout(resolve, Math.max(1, delay)));
                    }
                }
            }
        } catch (error: any) {
            // Fallback to simple movement
            try {
                const pageToUse = context || this.page;
                await pageToUse.mouse.move(targetX, targetY, { steps: 10 });
                this.lastMousePosition = { x: targetX, y: targetY };
            } catch (fallbackError: any) {
                // Silently fail
            }
        }
    }

    /**
     * Simulate human-like scrolling
     * @param {number} distance - Scroll distance (positive = down, negative = up)
     * @param {number} steps - Number of scroll steps
     */
    async humanScroll(distance: number, steps: number = 5): Promise<void> {
        const stepDistance = distance / steps;
        
        for (let i = 0; i < steps; i++) {
            await this.page.mouse.wheel(0, stepDistance);
            await this.page.waitForTimeout(this.randomDelay(100, 300));
        }
    }

    /**
     * Simulate Akamai-friendly human behavior on page load
     * This includes random clicks, movements, and jitter to generate clean sensor data
     */
    async simulateAkamaiHumanBehavior(logFunction: Function = console.log): Promise<void> {
        const startTime = Date.now();
        const MAX_DURATION = 8000; // Maximum 8 seconds safety limit
        
        try {
            // Validate page is available
            if (!this.page || this.page?.isClosed()) {
                return; // Silently skip if page unavailable
            }
            
            logFunction('Simulating Akamai human behavior');
            
            // Get viewport size (synchronous API; do not chain .catch)
            const viewportSize = this.page.viewportSize();
            if (!viewportSize) return;
            
            const width = viewportSize.width || 1920;
            const height = viewportSize.height || 1080;
            
            // Set initial cursor position
            const startX = Math.random() * (width * 0.6) + (width * 0.2);
            const startY = Math.random() * (height * 0.6) + (height * 0.2);
            await this.page.mouse.move(startX, startY);
            this.lastMousePosition = { x: startX, y: startY };
            
            // Initial pause
            await this.page.waitForTimeout(300 + Math.random() * 500);
            
            // Perform 5 random actions (completes in ~3-5 seconds)
            for (let i = 0; i < 5; i++) {
                // Safety checks
                if (Date.now() - startTime > MAX_DURATION) return;
                if (!this.page || this.page?.isClosed()) return;
                
                // Wait between actions
                await this.page.waitForTimeout(400 + Math.random() * 300);
                
                const actionType = Math.random();
                
                if (actionType < 0.5) {
                    // Mouse movement (50% chance)
                    const targetX = Math.random() * (width * 0.9) + (width * 0.05);
                    const targetY = Math.random() * (height * 0.9) + (height * 0.05);
                    await this.moveMouseRealistically(targetX, targetY);
                    
                    // Add jitter
                    const jitterX = targetX + (Math.random() - 0.5) * 20;
                    const jitterY = targetY + (Math.random() - 0.5) * 20;
                    await this.page.mouse.move(jitterX, jitterY);
                    this.lastMousePosition = { x: jitterX, y: jitterY };
                    
                } else if (actionType < 0.70) {
                    // Safe click (20% chance)
                    const centerX = width / 2;
                    const clickX = Math.random() < 0.5 
                        ? Math.random() * Math.max(50, centerX - 400)
                        : (centerX + 400) + Math.random() * Math.max(50, width - (centerX + 400));
                    const clickY = 150 + Math.random() * Math.max(100, height - 450);
                    
                    await this.moveMouseRealistically(clickX, clickY);
                    await this.page.waitForTimeout(80 + Math.random() * 150);
                    await this.page.mouse.down();
                    await this.page.waitForTimeout(40 + Math.random() * 80);
                    await this.page.mouse.up();
                    
                } else if (actionType < 0.85) {
                    // Small scroll (15% chance)
                    const scrollAmount = (Math.random() - 0.5) * 200;
                    await this.page.mouse.wheel(0, scrollAmount);
                    await this.page.waitForTimeout(150 + Math.random() * 200);
                    
                } else {
                    // Jitter movements (15% chance)
                    const currentX = this.lastMousePosition.x;
                    const currentY = this.lastMousePosition.y;
                    const jitterSteps = 2 + Math.floor(Math.random() * 3);
                    
                    for (let j = 0; j < jitterSteps; j++) {
                        if (!this.page || this.page?.isClosed()) return;
                        
                        const jitterX = currentX + (Math.random() - 0.5) * 30;
                        const jitterY = currentY + (Math.random() - 0.5) * 30;
                        await this.page.mouse.move(jitterX, jitterY);
                        this.lastMousePosition = { x: jitterX, y: jitterY };
                        await this.page.waitForTimeout(60 + Math.random() * 100);
                    }
                }
            }
            
            // Final settling movement
            const finalX = this.lastMousePosition.x + (Math.random() - 0.5) * 10;
            const finalY = this.lastMousePosition.y + (Math.random() - 0.5) * 10;
            await this.page.mouse.move(finalX, finalY);
            this.lastMousePosition = { x: finalX, y: finalY };
            
        } catch (error: any) {
            // Silent fail - don't throw errors or log unless critical
            if (error.message && !error.message.includes('closed') && !error.message.includes('destroyed')) {
                logFunction(`⚠️ Akamai simulation error: ${error.message}`);
                return;
            }
        }
    }

    /**
     * Quick check for browser error pages (language-agnostic)
     * Checks for specific CSS classes/IDs that identify error pages
     * @returns {boolean} True if error page detected, false otherwise
     */
    async browser_detectErrorPageQuick(): Promise<boolean> {
        try {
            // Check for the neterror class on body (most reliable universal indicator)
            const hasBodyClass = await this.page.locator('body.neterror').count() > 0;
            
            // Check for main-frame-error element with interstitial-wrapper class
            const hasMainFrameError = await this.page.locator('#main-frame-error.interstitial-wrapper').count() > 0;
            
            // Check for sub-frame-error element
            const hasSubFrameError = await this.page.locator('#sub-frame-error').count() > 0;
            
            return hasBodyClass || hasMainFrameError || hasSubFrameError;
        } catch (error) {
            return false;
        }
    }

    


    async browser_navigate(url: string, logFunction: Function = console.log): Promise<boolean> {
        const maxRetries = 2;
        let lastError: any = null;
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                //logFunction(`Navigating to ${url} (attempt ${attempt}/${maxRetries})`);
                
                // Navigate and wait for DOM to load first
                // We need actual page content for realistic mouse movements
                await this.page.goto(url, { 
                    waitUntil: 'domcontentloaded',
                    timeout: 30000
                });
                
                // Start Akamai-friendly human behavior on loaded page
                // This simulates a real user who sees the page, then starts interacting
                // The simulation itself has built-in delays for realism
                //await this.simulateAkamaiHumanBehavior(logFunction);
                
                //logFunction(`✅ Successfully navigated to ${url}`);
                return true;
                
            } catch (error: any) {
                lastError = error;
                //logFunction(`Navigation attempt ${attempt} failed: ${error.message}`);
                
                // If this isn't the last attempt, try to refresh the page
                if (attempt < maxRetries) {
                    try {
                        //logFunction(`Refreshing page before retry ${attempt + 1}...`);
                        await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 });
                        //logFunction(`Page refreshed successfully`);
                        
                        // Wait a bit before retrying
                        await this.page.waitForTimeout(2000);
                        
                    } catch (refreshError: any) {
                       // logFunction(`Page refresh failed: ${refreshError.message}`);
                        // Continue to next attempt even if refresh fails
                    }
                }
            }
        }
        
        // All attempts failed
        logFunction(`Failed to navigate to ${url} after ${maxRetries} attempts`);
        throw lastError;
    }

    async stabilizePosition(selector: string, elementName: string, context: any, timeoutSeconds: number, logFunction: Function): Promise<boolean> {
        let previousPosition: any = null;
        let stableCount = 0;
        const requiredStableCount = 3; // Require 3 consecutive stable positions
        
        for (let i = 0; i < 30; i++) {
            try {
                // Use the correct context for evaluation
                const pageToUse = context || this.page;
                const selectorToUse = selector; // Capture selector in local variable
                const position = await pageToUse.evaluate((sel: string) => {
                    const button = document.querySelector(sel);
                    if (button && (button as any).offsetParent !== null) {
                        const rect = button.getBoundingClientRect();
                        return {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        };
                    }
                    return null;
                }, selectorToUse);
                
                if (position) {
                    // Check if position is the same as previous
                    if (previousPosition && Math.abs(position.x - previousPosition.x) < 5 && Math.abs(position.y - previousPosition.y) < 5) {
                        stableCount++;
                    
                        if (stableCount >= requiredStableCount) {
                            return true;
                        }
                    } else {
                        stableCount = 0; // Reset if position changed
                    }
                    
                    previousPosition = position;
                }
            } catch (evalError: any) {
                logFunction(`${evalError.message}`);
            }
            
            // Wait 200ms before next check
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        return false;
    }

    /**
     * Robust click that waits up to specified seconds for element with retry logic
     * @param {string} selector - CSS selector to click
     * @param {string} elementName - Name for logging
     * @param {Object} context - Page or frame context to use
     * @param {number} maxRetries - Maximum number of retries (default: 2)
     * @param {number} timeoutSeconds - Timeout in seconds (default: 60)
     * @param {Function} logFunction - Optional logging function
     * @param {string} mode - Mode for clicking, stabilize will wait for the element to be on the same place for 3 seconds before clicking
     * @returns {boolean} - True if clicked, false if timeout
     */
    async robustClick(
        selector: string, 
        elementName: string = 'element', 
        context: any = null, 
        maxRetries: number = 3, 
        timeoutSeconds: number = 60, 
        logFunction: Function = console.log, 
        mode: string = 'default',
        throwErrors: boolean = true, 
        fastMode: boolean = false
    ): Promise<boolean> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                const pageContext = context || this.page;

                // added for fifa
                if(selector === 'button[aria-label="My Account"]' || selector === 'a[href*="fifa-fwc26-us.tickets.fifa.com"]' || selector === 'a[label="Sign In"]' || selector === '[class*="pop-up_closeIcon"]'){
                    // click on accept cookie button
                    try{
                        const cookieElement = pageContext.locator('div[class="onetrust-pc-dark-filter ot-fade-in"]');
                        const count = await cookieElement.count();
                        if (count > 0) {
                            await cookieElement.evaluate(element => element.remove());
                        }
                    }catch(error: any){
                        // Silently continue - no logging to prevent console errors
                    }
                   
                }
                
                // Wait for element with specified timeout
                const found = await this.waitForElementRobust(selector, elementName, pageContext, timeoutSeconds, logFunction);
                if (!found) {
                    if (attempt === maxRetries) {
                        return false;
                    }
                    continue;
                }
                // Stabilize mode will wait for element to be (still) before clickijng
                if(mode === 'stabilize'){
                    const stabilized = await this.stabilizePosition(selector, elementName, pageContext, timeoutSeconds, logFunction);
                    if(!stabilized){
                        return false;
                    }
                }

                // Click with realistic movement (within context)
                await this.humanClickInContext(selector, pageContext, logFunction, fastMode);
                return true;
                
            } catch (error: any) {
                if(!throwErrors){
                    return false;
                }
                console.error(`Error clicking ${elementName} on attempt ${attempt}:`, error.message);
                
                // If it's a proxy timeout, re-throw to trigger proxy retry
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error;
                }
                
                if (attempt === maxRetries) {
                    return false;
                }
                
                // Wait before retry
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Robust form fill that waits up to specified seconds for field with retry logic
     * @param {string} selector - CSS selector for field
     * @param {string} value - Value to fill
     * @param {string} fieldName - Name for logging
     * @param {Object} context - Page or frame context to use
     * @param {number} maxRetries - Maximum number of retries (default: 2)
     * @param {number} timeoutSeconds - Timeout in seconds (default: 60)
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean} - True if filled, false if timeout
     */
    async robustFill(
        selector: string, 
        value: string, 
        fieldName: string = 'field',
        context: any = null,
        maxRetries: number = 3, 
        timeoutSeconds: number = 60, 
        logFunction: Function = console.log
    ): Promise<boolean> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                
                const pageContext = context || this.page;
                
                // Wait for field with specified timeout
                const found = await this.waitForElementRobust(selector, fieldName, pageContext, timeoutSeconds, logFunction);
                if (!found) {
                    if (attempt === maxRetries) {
                        return false;
                    }
                    continue;
                }
                
                const field = pageContext.locator(selector).first();
                
                // Click field (iframe-safe): if context has no mouse API, use direct locator.click
                const hasMouse = pageContext && pageContext.mouse && typeof pageContext.mouse.down === 'function';
                if (!hasMouse) {
                    await field.scrollIntoViewIfNeeded();
                    await field.click();
                    await new Promise(resolve => setTimeout(resolve, this.randomDelay(120, 220)));
                } else {
                    // Click field realistically
                    await this.humanClickInContext(selector, pageContext, logFunction);
                    await new Promise(resolve => setTimeout(resolve, this.randomDelay(140, 280)));
                }
                
                // Clear field completely
                await field.selectText();
                await field.press('Delete');
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(120, 260)));
                
                // Type with realistic key events and timing (works for both page and iframe once focused)
                const isWordBoundary = (c: string) => /[\s\-_/.,]/.test(c);
                const isSpecial = (c: string) => /[!@#$%^&*()+=\[\]{};:'"\\|,.<>\/?]/.test(c);
                const keyboard = (this.page && this.page.keyboard) || (pageContext.keyboard);
                // Focus via click already; ensure active element
                try { await field.focus(); } catch {}

                let burstCounter = 0;
                for (let i = 0; i < value.length; i++) {
                    const char = value[i];
                    const prev = i > 0 ? value[i - 1] : '';
                    const next = i < value.length - 1 ? value[i + 1] : '';

                    // Base delay bands
                    let min = 45, max = 120; // baseline for normal letters
                    if (/[A-Z]/.test(char)) { min = 110; max = 260; }
                    if (/[0-9]/.test(char)) { min = 90; max = 220; }
                    if (isSpecial(char)) { min = 140; max = 320; }
                    if (isWordBoundary(prev) || isWordBoundary(char)) { min += 40; max += 80; }

                    // Burst typing: if in middle of a word, occasionally speed up
                    if (!isWordBoundary(char) && !isWordBoundary(prev) && Math.random() < 0.15 && burstCounter < 6) {
                        min = 25; max = 65; burstCounter++;
                    } else if (isWordBoundary(char)) {
                        burstCounter = 0;
                    }

                    // Occasional short hesitation before rare chars or boundaries
                    if (isSpecial(char) || isWordBoundary(char)) {
                        if (Math.random() < 0.25) {
                            await new Promise(resolve => setTimeout(resolve, 120 + Math.random() * 240));
                        }
                    }

                    // Type using keyboard to emit full key events
                    await keyboard.type(char, { delay: Math.floor(min + Math.random() * (max - min)) });

                    // Occasional micro-pause mid-word
                    if (!isWordBoundary(char) && Math.random() < 0.08) {
                        await new Promise(resolve => setTimeout(resolve, 80 + Math.random() * 180));
                    }

                    // Context-aware typo correction: higher chance on long words or special chars
                    const longWordContext = !isWordBoundary(char) && !isWordBoundary(prev) && !isWordBoundary(next);
                    if ((isSpecial(char) || longWordContext) && Math.random() < 0.035 && i > 2) {
                        await keyboard.press('Backspace');
                        await new Promise(resolve => setTimeout(resolve, 60 + Math.random() * 120));
                        await keyboard.type(char, { delay: Math.floor(min + Math.random() * (max - min)) });
                    }
                }
                
                // Trigger events
                await field.dispatchEvent('input');
                await field.dispatchEvent('change');
                await field.dispatchEvent('blur');
                
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(200, 420)));
                return true;
                
            } catch (error: any) {
                console.error(`Error filling ${fieldName} on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    logFunction(`Failed to fill ${fieldName} after ${maxRetries} attempts`);
                    return false;
                }
                
                // Wait before retry
                logFunction(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Robust dropdown selection that waits up to specified seconds with realistic clicking and retry logic
     * @param {string} selector - CSS selector for dropdown
     * @param {string} value - Value to select
     * @param {string} fieldName - Name for logging
     * @param {Object} context - Page or frame context to use
     * @param {number} maxRetries - Maximum number of retries (default: 2)
     * @param {number} timeoutSeconds - Timeout in seconds (default: 60)
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean} - True if selected, false if timeout
     */
    async robustSelect(selector: string, value: string, fieldName: string = 'dropdown', context: any = null, maxRetries: number = 2, timeoutSeconds: number = 60, logFunction: Function = console.log, mode: string = 'default' ): Promise<boolean> {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                
                const pageContext = context || this.page;
                
                // Wait for dropdown with specified timeout
                const found = await this.waitForElementRobust(selector, fieldName, pageContext, timeoutSeconds, logFunction);
                if (!found) {
                    logFunction(`${fieldName} not found on attempt ${attempt}`);
                    if (attempt === maxRetries) {
                        return false;
                    }
                    continue;
                }
                
                const dropdown = pageContext.locator(selector).first();
                
                // Click dropdown realistically to open it
                await this.humanClickInContext(selector, pageContext, logFunction);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(500, 1000)));
                
                // Try realistic option clicking first
                try {
                    const stringValue = String(value);
                    const optionSelector = `${selector} option[value="${stringValue}"]`;
                    const option = pageContext.locator(optionSelector);
                    
                    if (await option.isVisible({ timeout: 3000 })) {
                        await this.humanClickInContext(optionSelector, pageContext, logFunction);
                        await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                        // TODO CHECK IF WORKS
                        if(mode === 'exitDropdown'){
                            // Try multiple ways to close dropdown
                            try {
                                await pageContext.keyboard.press('Escape');
                            } catch {
                                await pageContext.keyboard.press('Tab');
                            }
                            await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                        }
                        return true;
                    }
                } catch (error) {
                    logFunction(`Realistic option clicking failed, using programmatic selection...`);
                }
                
                // Fallback to programmatic selection
                // Convert value to string for Playwright compatibility
                const stringValue = String(value);
                await dropdown.selectOption(stringValue);
                
                // Trigger events
                await dropdown.dispatchEvent('change');
                await dropdown.dispatchEvent('blur');
                
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                
                // Handle exitDropdown mode for programmatic selection too
                if(mode === 'exitDropdown'){
                    // Try multiple ways to close dropdown
                    try {
                        await pageContext.keyboard.press('Escape');
                    } catch {
                        await pageContext.keyboard.press('Tab');
                    }
                    await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
                }
                
                return true;
                
            } catch (error: any) {
                console.error(`Error selecting ${fieldName} on attempt ${attempt}:`, error.message);
                
                if (error.message.includes('PROXY_TIMEOUT')) {
                    throw error; // Re-throw to trigger proxy retry
                }
                
                if (attempt === maxRetries) {
                    logFunction(`Failed to select ${fieldName} after ${maxRetries} attempts`);
                    return false;
                }
                
                // Wait before retry
                logFunction(`Waiting 3 seconds before retry...`);
                await new Promise(resolve => setTimeout(resolve, 3000));
            }
        }
        return false;
    }

    /**
     * Click login button with multiple selector attempts
     * @param {Array} loginSelectors - Array of CSS selectors to try
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean} - True if clicked, false otherwise
     */
    async clickLoginButton(loginSelectors: string[] = [
        'button[id="loginFormSubmitBtn"]',
        'button[data-skbuttonvalue="login"]',
        'button[type="submit"]',
        'button:has-text("SIGN IN")',
        '.btn-primary'
    ], logFunction: Function = console.log): Promise<boolean> {
        try {
            
            let loginClicked = false;
            for (const selector of loginSelectors) {
                try {
                    const button = this.page.locator(selector).first();
                    if (await button.isVisible({ timeout: 2000 })) {
                        await this.humanClick(selector);
                        loginClicked = true;
                        break;
                    }
                } catch (error) {
                    continue;
                }
            }
            
            if (!loginClicked) {
                // Try browser evaluation as fallback
                const clicked = await this.page.evaluate(() => {
                    const button = document.querySelector('button[id="loginFormSubmitBtn"]') || 
                                 document.querySelector('button[data-skbuttonvalue="login"]');
                    if (button && (button as any).offsetParent !== null) {
                        (button as any).click();
                        return true;
                    }
                    return false;
                });
                
                if (clicked) {
                    loginClicked = true;
                }
            }
            
            if (!loginClicked) {
                logFunction('Login button not found');
            }
            
            // Wait after clicking
            await this.page.waitForTimeout(this.randomDelay(1000, 2000));
            return loginClicked;
            
        } catch (error: any) {
            console.error('Error clicking login button:', error.message);
            throw error;
        }
    }

    /**
     * Click login button with robust method (60-second timeout)
     * @param {Array} loginSelectors - Array of CSS selectors to try
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean} - True if clicked, false otherwise
     */
    async clickLoginButtonRobust(loginSelectors: string[] = [
        'button[id="loginFormSubmitBtn"]',
        'button[data-skbuttonvalue="login"]',
        'button[type="submit"]',
        'button:has-text("SIGN IN")',
        '.btn-primary'
    ], logFunction: Function = console.log): Promise<boolean> {
        try {      
            let loginClicked = false;
            for (const selector of loginSelectors) {
                loginClicked = await this.robustClick(selector, `Login button (${selector})`, null, 2, 60, logFunction);
                if (loginClicked) {
                    break;
                }
            }
            
            return loginClicked;
            
        } catch (error: any) {
            console.error('Error clicking login button with robust method:', error.message);
            return false;
        }
    }

    /**
     * Select dropdown option realistically with Tab navigation
     * @param {string} selector - CSS selector for dropdown
     * @param {string} value - Value to select
     * @param {string} fieldName - Name for logging
     * @param {Object} context - Page or frame context to use
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean} - True if selected, false otherwise
     */
    async selectDropdownRealistically(selector: string, value: string, fieldName: string, context: any = null, logFunction: Function = console.log): Promise<boolean> {
        try {
            
            const pageContext = context || this.page;
            
            // Wait for dropdown
            const found = await this.waitForElementRobust(selector, fieldName, pageContext, 60, logFunction);
            if (!found) return false;
            
            // Click dropdown to focus
            const clicked = await this.robustClick(selector, fieldName, pageContext, 2, 60, logFunction);
            if (!clicked) return false;
            
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(500, 1000)));
            
            const dropdown = pageContext.locator(selector).first();
            
            // Try programmatic selection
            await dropdown.selectOption(value);
            
            // Wait for selection to process
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(300, 600)));
            
            // Verify the selection was successful
            const selectedValue = await dropdown.inputValue();
            
            // If selection didn't work, try again
            if (selectedValue !== value) {
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(500, 1000)));
                await dropdown.selectOption(value);
                await new Promise(resolve => setTimeout(resolve, this.randomDelay(500, 1000)));
                
                // Check again
                const retryValue = await dropdown.inputValue();
                logFunction(`Retry ${fieldName} selection: expected=${value}, actual=${retryValue}`);
            }
            
            // Trigger events
            await dropdown.dispatchEvent('change');
            await dropdown.dispatchEvent('blur');
            
            logFunction(`${fieldName} selected: ${value}`);
            await new Promise(resolve => setTimeout(resolve, this.randomDelay(500, 1000)));
            return true;
            
        } catch (error: any) {
            logFunction(`Error selecting ${fieldName}: ${error.message}`);
            return false;
        }
    }

    /**
     * Fill a field with realistic typing behavior
     * @param {string} selector - CSS selector for field
     * @param {string} value - Value to fill
     * @param {string} fieldName - Name for logging
     * @param {Object} context - Page or frame context to use
     * @param {Function} logFunction - Optional logging function
     * @returns {boolean} - True if filled successfully, false otherwise
     */
    async fillFieldRealistically(selector: string, value: string, fieldName: string, context: any = null, logFunction: Function = console.log): Promise<boolean> {
        try {
            
            const pageContext = context || this.page;
            const field = pageContext.locator(selector).first();
            
            // Click and focus on field with realistic movement
            await this.humanClick(selector);
            await this.page.waitForTimeout(this.randomDelay(200, 400));
            
            // Clear field completely
            await field.selectText();
            await field.press('Delete');
            await this.page.waitForTimeout(this.randomDelay(200, 400));
            
            // Type character by character with realistic delays
            for (let i = 0; i < value.length; i++) {
                const char = value[i];
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
            const filledValue = await field.inputValue();
            
            // Small pause after filling
            await this.page.waitForTimeout(this.randomDelay(300, 600));
            return true;
            
        } catch (error: any) {
            return false;
        }
    }

    /**
     * Robust page detection and switching mechanism
     * Detects new pages opened by clicks and switches to the correct one
     * @param {Object} context - Browser context
     * @param {Function} logFunction - Logging function
     * @returns {Promise<boolean>} Success status
     */
    async detectAndSwitchToNewPage(context: any, logFunction: Function): Promise<boolean> {
        if (!context) {
            logFunction('Context not available for page detection', 'error');
            return false;
        }

        const maxAttempts = 14; // Increased attempts for better reliability
        const baseWaitTime = 1000; // Base wait time in ms
        const originalPageCount = context.pages().length;
        const originalUrl = this.page?.url() || '';
        
        //logFunction(`Starting page detection - Original page count: ${originalPageCount}, URL: ${originalUrl}`);
        
        // Set up page event listener for immediate detection
        let newPageDetected: any = null;
        const pageListener = (page: any) => {
           // logFunction(`New page event detected: ${page.url()}`);
            if (page.url().includes('auth.fifa.com') || page.url().includes('fifa.com') || page.url().includes('pkpcontroller')) {
                newPageDetected = page;
            }
        };
        
        context.on('page', pageListener);
        
        try {
            for (let attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    //logFunction(`Detecting new page... (Attempt ${attempt}/${maxAttempts})`);
                    
                    // Check if we already detected a new page via event listener
                    if (newPageDetected) {
                        //logFunction(`Switching to event-detected page: ${newPageDetected.url()}`);
                        this.setPage(newPageDetected);
                        await newPageDetected.waitForLoadState('domcontentloaded', { timeout: 30000 });
                        return true;
                    }
                    
                    // Get all current pages
                    const pages: any[] = context.pages();
                    //logFunction(`Current pages count: ${pages.length}`);
                    
                    // Strategy 1: Look for pages with auth.fifa.com URL
                    for (let i = pages.length - 1; i >= 0; i--) {
                        const page = pages[i];
                        const url = page.url();
                        //logFunction(`Page ${i} URL: ${url}`);
                        
                        if (url.includes('auth.fifa.com') || url.includes('pkpcontroller')) {
                            //logFunction(`Found auth page at index ${i}, switching to it`);
                            this.setPage(page);
                            
                            // Wait for the page to be fully loaded
                            try {
                                await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
                                //await page.waitForLoadState('networkidle', { timeout: 15000 });
                                //logFunction(`Successfully switched to auth page: ${page.url()}`);
                                return true;
                            } catch (loadError: any) {
                                //logFunction(`Page load timeout, but continuing with auth page: ${loadError.message}`, 'warn');
                                return true; // Still return true as we found the auth page
                            }
                        }
                    }
                    
                    // Strategy 2: Look for any new page (not the original)
                    if (pages.length > originalPageCount) {
                        for (let i = pages.length - 1; i >= 0; i--) {
                            const page = pages[i];
                            const url = page.url();
                            
                            // Skip if it's the same as original page
                            if (url === originalUrl) continue;
                            
                            // Check if it's a FIFA-related domain
                            if (url.includes('fifa.com') || url.includes('auth.fifa.com') || url.includes('tickets.fifa.com') || url.includes('pkpcontroller')) {
                                //logFunction(`Found new FIFA page at index ${i}, switching to it`);
                                this.setPage(page);
                                
                                // Wait for the page to be fully loaded
                                try {
                                    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
                                    //await page.waitForLoadState('networkidle', { timeout: 15000 });
                                    //logFunction(`Successfully switched to FIFA page: ${page.url()}`);
                                    return true;
                                } catch (loadError: any) {
                                    //logFunction(`Page load timeout, but continuing with FIFA page: ${loadError.message}`, 'warn');
                                    return true; // Still return true as we found the FIFA page
                                }
                            }
                        }
                    }
                    
                    // Strategy 3: Wait for page count to increase or new page to load
                    if (attempt < maxAttempts) {
                        const waitTime = Math.min(baseWaitTime * attempt, 5000); // Progressive wait, max 5s
                        //logFunction(`No new page detected, waiting ${waitTime}ms before retry...`);
                        await new Promise(resolve => setTimeout(resolve, waitTime));
                        
                        // Check if page count increased during wait
                        const newPages: any[] = context.pages();
                        if (newPages.length > pages.length) {
                            //logFunction(`Page count increased from ${pages.length} to ${newPages.length}, checking new pages...`);
                            // Continue to next iteration to check the new pages
                            continue;
                        }
                    }
                    
                } catch (error: any) {
                    logFunction(`Page detection attempt ${attempt} failed: ${error.message}`, 'warn');
                    
                    if (attempt < maxAttempts) {
                        const waitTime = baseWaitTime * attempt;
                        logFunction(`Waiting ${waitTime}ms before retry...`);
                        await new Promise(resolve => setTimeout(resolve, waitTime));
                    }
                }
            }
            
        } finally {
            // Clean up event listener
            context.off('page', pageListener);
        }
        
        logFunction(`Failed to detect new page after ${maxAttempts} attempts`, 'error');
        return false;
    }

    // will return false if still blocked, true if not blocked
    async handleCaptchaBlock(logFunction: Function): Promise< string> {
        try{
            const isCaptchaBlocked = await this.checkForCaptchaBlock();
            if (isCaptchaBlocked) {
                logFunction(`Captcha block detected, waiting 120 seconds to reload page...`);
                await this.page.waitForTimeout(120000);
                await this.page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
               
            }
            let stillBlocked = await this.checkForCaptchaBlock();
            if(stillBlocked){
                return "BLOCKED";
            }

            return "UNBLOCKED";
        }catch(error: any){
            logFunction(`Error handling captcha block: ${error.message}`);
            return "BLOCKED";
        }
    }



    async checkForCaptchaBlock(): Promise<boolean> {
        try {
            // Only use Method 2: Check for specific geo.captcha-delivery.com/captcha/ iframe
            const iframes = await this.page.locator('iframe').all();
            for (const iframe of iframes) {
                try {
                    const src = await iframe.getAttribute('src');
                    if (src && (src.includes('https://geo.captcha-delivery.com/interstitial/') || src.includes('https://geo.captcha-delivery.com/captcha/'))) {
                        return true;
                    }
                } catch (error: any) {
                    throw new Error('PROXY_TIMEOUT');
                }
            }
            return false;
        } catch (error: any) {
            throw new Error('PROXY_TIMEOUT');
        }
    }
}

export default HumanInteractions;