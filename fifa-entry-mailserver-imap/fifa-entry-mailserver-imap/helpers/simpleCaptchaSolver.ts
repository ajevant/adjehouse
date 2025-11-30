// Types and interfaces
interface Page {
    waitForSelector(selector: string, options?: any): Promise<any>;
    frameLocator(selector: string): any;
    locator(selector: string): any;
    waitForTimeout(ms: number): Promise<void>;
    mouse: any;
}

interface FrameLocator {
    locator(selector: string): any;
}

interface Element {
    waitFor(options?: any): Promise<void>;
    boundingBox(): Promise<any>;
    hover(): Promise<void>;
    click(): Promise<void>;
    isVisible(options?: any): Promise<boolean>;
    selectOption(value: string): Promise<void>;
    dispatchEvent(event: string): Promise<void>;
}

interface Locator {
    first(): Element;
    count(): Promise<number>;
    isVisible(options?: any): Promise<boolean>;
}

/**
 * Simple DataDome CAPTCHA Solver
 * Uses JavaScript-based solving without image processing dependencies
 */
class SimpleCaptchaSolver {
    private page: Page;
    private log: (message: string) => void;

    constructor(page: Page, logFunction?: (message: string) => void) {
        this.page = page;
        this.log = logFunction || console.log;
    }

    /**
     * Main method to solve the CAPTCHA
     */
    async solveCaptcha(): Promise<boolean> {
        try {
            this.log('🔍 Starting simple CAPTCHA solving process...');
            
            // Wait for CAPTCHA to load
            await this.waitForCaptchaLoad();
            
            // Try JavaScript-based solving
            const jsSolved: boolean = await this.solveWithJavaScript();
            if (jsSolved) {
                this.log('CAPTCHA solved with JavaScript method!');
                return true;
            }
            
            // Try mouse-based solving
            const mouseSolved: boolean = await this.solveWithMouse();
            if (mouseSolved) {
                this.log('CAPTCHA solved with mouse method!');
                return true;
            }
            
            this.log('❌ All solving methods failed');
            return false;
            
        } catch (error: any) {
            this.log(`❌ CAPTCHA solving failed: ${error.message}`);
            return false;
        }
    }

    /**
     * Wait for CAPTCHA to fully load
     */
    async waitForCaptchaLoad(): Promise<void> {
        this.log('Waiting for CAPTCHA to load...');
        
        // Wait for the DataDome iframe to be visible
        await this.page.waitForSelector('iframe[src*="captcha-delivery.com"]', { timeout: 10000 });
        
        // Get iframe element and inspect its content
        const iframeElement: any = this.page.locator('iframe[src*="captcha-delivery.com"]').first();
        const iframe: any = await iframeElement.contentFrame();
        
        if (iframe) {
            this.log('Successfully accessed iframe content');
            
            // Wait for canvas elements to be present
            try {
                await iframe.locator('canvas').first().waitFor({ timeout: 10000 });
                this.log('Canvas elements found in iframe');
            } catch (error: any) {
                this.log('⚠️ No canvas elements found, trying other selectors...');
                
                // Try to find slider elements instead
                const sliderElements: number = await iframe.locator('[class*="slider"], [class*="track"], [class*="button"]').count();
                this.log(`🔍 Found ${sliderElements} potential slider elements`);
            }
        } else {
            this.log('❌ Could not access iframe content');
        }
        
        // Wait a bit more for the CAPTCHA content to load
        await this.page.waitForTimeout(3000);
        
        this.log('CAPTCHA loaded');
    }

    /**
     * Inspect iframe DOM structure for debugging
     */
    async inspectIframeStructure(): Promise<void> {
        try {
            this.log('🔍 Inspecting iframe DOM structure...');
            
            // Use frameLocator to find elements
            const frameLocator: FrameLocator = this.page.frameLocator('iframe[src*="captcha-delivery.com"]');
            
            // Find common slider/track elements
            const sliderElements: number = await frameLocator.locator('[class*="slider"], [class*="track"], [class*="button"], [class*="handle"]').count();
            const canvasElements: number = await frameLocator.locator('canvas').count();
            const buttonElements: number = await frameLocator.locator('button').count();
            
            this.log(`🔍 Found ${sliderElements} slider elements, ${canvasElements} canvas elements, ${buttonElements} button elements`);
            
        } catch (error: any) {
            this.log(`⚠️ Error inspecting iframe: ${error.message}`);
        }
    }

    /**
     * Solve CAPTCHA using JavaScript manipulation
     */
    async solveWithJavaScript(): Promise<boolean> {
        try {
            this.log('🔧 Attempting JavaScript-based CAPTCHA solving...');
            
            // Use frameLocator approach for iframe interactions
            const frameLocator: FrameLocator = this.page.frameLocator('iframe[src*="captcha-delivery.com"]');
            
            // Inspect the iframe structure for debugging
            await this.inspectIframeStructure();
            
            // Try to find and manipulate the slider programmatically
            const sliderButton: Element = frameLocator.locator('.slider-button, .slider-handle, [class*="slider"]').first();
            
            if (await sliderButton.isVisible()) {
                this.log('Slider button found, attempting to solve...');
                
                // Try to click and drag the slider
                const sliderTrack: Element = frameLocator.locator('.slider-track, [class*="track"]').first();
                
                if (await sliderTrack.isVisible()) {
                    // Get track dimensions
                    const trackBox: any = await sliderTrack.boundingBox();
                    if (trackBox) {
                        // Calculate target position (usually around 30% of track width)
                        const targetPosition: number = Math.floor(trackBox.width * 0.3);
                        
                        this.log(`🎯 JavaScript slider position: ${targetPosition}px`);
                        
                        // Click and drag the slider with real element interactions
                        await sliderButton.hover();
                        await this.page.waitForTimeout(100);
                        
                        // Press mouse down on slider
                        await this.page.mouse.down();
                        await this.page.waitForTimeout(50);
                        
                        // Move to target position with human-like movement
                        const steps: number = 10;
                        const startX: number = trackBox.x;
                        const startY: number = trackBox.y + trackBox.height / 2;
                        const endX: number = trackBox.x + targetPosition;
                        const endY: number = startY;
                        
                        for (let i = 0; i <= steps; i++) {
                            const progress: number = i / steps;
                            const currentX: number = startX + (endX - startX) * progress;
                            const currentY: number = startY + Math.sin(progress * Math.PI) * 5; // Slight curve
                            
                            await this.page.mouse.move(currentX, currentY);
                            await this.page.waitForTimeout(20 + Math.random() * 30);
                        }
                        
                        // Release mouse
                        await this.page.mouse.up();
                        
                        // Wait for processing
                        await this.page.waitForTimeout(2000);
                        
                        return await this.checkIfSolved();
                    }
                }
                
                // Fallback: just click the slider button
                this.log('Fallback: clicking slider button...');
                await sliderButton.click();
                await this.page.waitForTimeout(2000);
                
                return await this.checkIfSolved();
            }
            
            return false;
            
        } catch (error: any) {
            this.log(`❌ JavaScript solving failed: ${error.message}`);
            return false;
        }
    }

    /**
     * Solve CAPTCHA using mouse movements
     */
    async solveWithMouse(): Promise<boolean> {
        try {
            this.log('🖱️ Attempting mouse-based CAPTCHA solving...');
            
            // Use frameLocator approach for iframe interactions
            const frameLocator: FrameLocator = this.page.frameLocator('iframe[src*="captcha-delivery.com"]');
            
            // Find the slider element
            const slider: Element = frameLocator.locator('.slider-button, .slider-handle, [class*="slider"]').first();
            
            if (await slider.isVisible()) {
                // Get slider bounds
                const sliderBounds: any = await slider.boundingBox();
                if (!sliderBounds) {
                    this.log('❌ Could not find slider element');
                    return false;
                }
                
                // Get track bounds for accurate positioning
                const track: Element = frameLocator.locator('.slider-track, [class*="track"]').first();
                const trackBounds: any = await track.boundingBox();
                
                let targetX: number, targetY: number;
                
                if (trackBounds) {
                    // Calculate target position (30% of track width)
                    const targetPosition: number = trackBounds.width * 0.3;
                    targetX = trackBounds.x + targetPosition;
                    targetY = trackBounds.y + trackBounds.height / 2;
                } else {
                    // Fallback: use slider bounds
                    const targetPosition: number = sliderBounds.width * 0.3;
                    targetX = sliderBounds.x + targetPosition;
                    targetY = sliderBounds.y + sliderBounds.height / 2;
                }
                
                this.log(`🎯 Mouse target position: (${targetX}, ${targetY})`);
                
                // Perform the drag
                await this.performMouseDrag(slider, targetX, targetY);
                
                // Wait for processing
                await this.page.waitForTimeout(3000);
                
                return await this.checkIfSolved();
            }
            
            return false;
            
        } catch (error: any) {
            this.log(`❌ Mouse solving failed: ${error.message}`);
            return false;
        }
    }

    /**
     * Perform mouse drag with human-like movement
     */
    async performMouseDrag(slider: Element, targetX: number, targetY: number): Promise<void> {
        try {
            // Get current position
            const currentBounds: any = await slider.boundingBox();
            const startX: number = currentBounds.x + currentBounds.width / 2;
            const startY: number = currentBounds.y + currentBounds.height / 2;
            
            this.log(`🎯 Dragging from (${startX}, ${startY}) to (${targetX}, ${targetY})`);
            
            // Use realistic element interactions
            await slider.hover();
            await this.page.waitForTimeout(100);
            
            // Press mouse down on slider
            await this.page.mouse.down();
            await this.page.waitForTimeout(50);
            
            // Move to target position with human-like movement
            const steps: number = 15;
            const deltaX: number = targetX - startX;
            const deltaY: number = targetY - startY;
            
            for (let i = 0; i <= steps; i++) {
                const progress: number = i / steps;
                
                // Add human-like curve and micro-movements
                const curve: number = Math.sin(progress * Math.PI) * 0.1;
                const microX: number = (Math.random() - 0.5) * 2;
                const microY: number = (Math.random() - 0.5) * 2;
                
                const currentX: number = startX + (deltaX * progress) + (curve * deltaY) + microX;
                const currentY: number = startY + (deltaY * progress) - (curve * deltaX) + microY;
                
                await this.page.mouse.move(currentX, currentY);
                await this.page.waitForTimeout(15 + Math.random() * 25);
            }
            
            // Release mouse
            await this.page.mouse.up();
            
            this.log('Mouse drag completed');
            
        } catch (error: any) {
            this.log(`❌ Error during mouse drag: ${error.message}`);
            
            // Fallback: try clicking the slider
            try {
                this.log('Fallback: clicking slider...');
                await slider.click();
                await this.page.waitForTimeout(1000);
            } catch (clickError: any) {
                this.log(`❌ Click fallback also failed: ${clickError.message}`);
            }
        }
    }

    /**
     * Check if the CAPTCHA has been solved
     */
    async checkIfSolved(): Promise<boolean> {
        try {
            // Wait a moment for any success indicators
            await this.page.waitForTimeout(2000);
            
            // Check for common success indicators
            const successSelectors: string[] = [
                'iframe[src*="captcha-delivery.com"]', // Iframe should disappear
                '.captcha-success',
                '.verification-success',
                '[class*="success"]'
            ];
            
            for (const selector of successSelectors) {
                try {
                    const element: Element = this.page.locator(selector).first();
                    const isVisible: boolean = await element.isVisible({ timeout: 1000 });
                    
                    if (selector.includes('iframe') && !isVisible) {
                        this.log('CAPTCHA iframe disappeared - likely solved');
                        return true;
                    } else if (!selector.includes('iframe') && isVisible) {
                        this.log('Success indicator found');
                        return true;
                    }
                } catch (e) {
                    // Continue checking other selectors
                }
            }
            
            // Check if we're back to the main page
            const mainContent: boolean = await this.page.locator('#main_content_lottery_applications').isVisible();
            if (mainContent) {
                this.log('Back to main content - CAPTCHA likely solved');
                return true;
            }
            
            return false;
            
        } catch (error: any) {
            this.log(`❌ Error checking if solved: ${error.message}`);
            return false;
        }
    }
}

export default SimpleCaptchaSolver;
