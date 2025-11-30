/**
 * Natural browser events and imperfections to evade bot detection
 * Injects realistic human errors, hesitations, and event sequences
 * OPTIMIZED: Fast but unpredictable - focuses on pattern breaking, not slowness
 */

export class NaturalEvents {
    private page: any;
    private eventCache: Map<string, number>; // Cache last event times to add variance

    constructor(page: any) {
        this.page = page;
        this.eventCache = new Map();
    }

    /**
     * Inject natural mouse events during movement (FAST - only 5% of the time)
     * Akamai tracks: mouseover, mouseenter, mouseleave, mouseout
     */
    async injectMouseEvents(x: number, y: number): Promise<void> {
        // Only inject 5% of the time to stay fast
        if (Math.random() > 0.05) return;
        
        try {
            await this.page.evaluate(({ x, y }: { x: number; y: number }) => {
                const el = document.elementFromPoint(x, y);
                if (el) {
                    el.dispatchEvent(new MouseEvent('mouseover', {
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y
                    }));
                }
            }, { x, y });
        } catch (error) {
            // Silent
        }
    }

    /**
     * Add micro-corrections to mouse movement (REDUCED - only on long distances)
     * @returns Adjusted target with micro-correction
     */
    addMicroCorrection(currentX: number, currentY: number, targetX: number, targetY: number): { x: number; y: number } {
        const distance = Math.sqrt(Math.pow(targetX - currentX, 2) + Math.pow(targetY - currentY, 2));
        
        // Only overshoot on long movements (>200px) and 15% of the time
        if (Math.random() < 0.15 && distance > 200) {
            const angle = Math.atan2(targetY - currentY, targetX - currentX);
            const overshoot = 3 + Math.random() * 7; // Reduced from 5-15
            
            return {
                x: targetX + Math.cos(angle) * overshoot,
                y: targetY + Math.sin(angle) * overshoot
            };
        }
        
        return { x: targetX, y: targetY };
    }

    /**
     * Add natural tremor to mouse position (MINIMAL - only 20% of the time)
     */
    addTremor(x: number, y: number): { x: number; y: number } {
        // Reduced from 60% to 20%
        if (Math.random() < 0.2) {
            return {
                x: x + (Math.random() - 0.5) * 1.5, // Reduced from 2px
                y: y + (Math.random() - 0.5) * 1.5
            };
        }
        return { x, y };
    }

    /**
     * Simulate scroll wheel imperfections (SUBTLE)
     */
    getImperfectScrollAmount(baseAmount: number): number {
        // Reduced variance from ±5-15% to ±3-8%
        const variance = 0.03 + Math.random() * 0.05;
        const sign = Math.random() < 0.5 ? -1 : 1;
        return Math.floor(baseAmount * (1 + sign * variance));
    }

    /**
     * Inject natural focus/blur event sequence with parent events
     * CRITICAL: Akamai tracks focusin on parents + pointerenter
     */
    async injectFocusEvents(selector: string): Promise<void> {
        try {
            await this.page.evaluate((sel: string) => {
                const el = document.querySelector(sel) as HTMLElement;
                if (el) {
                    // CRITICAL: Fire focusin on parent FIRST (bubbles up)
                    const parent = el.parentElement;
                    if (parent) {
                        parent.dispatchEvent(new FocusEvent('focusin', { 
                            bubbles: true,
                            composed: true 
                        }));
                    }
                    
                    // Fire pointerenter (Akamai tracks this)
                    el.dispatchEvent(new PointerEvent('pointerenter', {
                        bubbles: false,
                        cancelable: false,
                        pointerId: 1,
                        pointerType: 'mouse',
                        isPrimary: true
                    }));
                    
                    // Then focus events on element
                    el.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
                    el.dispatchEvent(new FocusEvent('focus', { bubbles: false }));
                }
            }, selector);
        } catch (error) {
            // Silent
        }
    }

    /**
     * Inject natural pointer events (FAST - 10% of the time)
     */
    async injectPointerEvents(x: number, y: number, eventType: 'down' | 'up' | 'move'): Promise<void> {
        // Only inject 10% of the time for speed
        if (Math.random() > 0.1) return;
        
        try {
            await this.page.evaluate(({ x, y, type }: { x: number; y: number; type: string }) => {
                const el = document.elementFromPoint(x, y);
                if (el) {
                    el.dispatchEvent(new PointerEvent('pointer' + type, {
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y,
                        pointerId: 1,
                        pointerType: 'mouse',
                        isPrimary: true
                    }));
                }
            }, { x, y, type: eventType });
        } catch (error) {
            // Silent
        }
    }

    /**
     * Simulate accidental double-click (RARE - 1% instead of 2%)
     */
    async maybeAccidentalDoubleClick(): Promise<boolean> {
        if (Math.random() < 0.01) {
            await this.page.waitForTimeout(50 + Math.random() * 80); // Reduced delay
            return true;
        }
        return false;
    }

    /**
     * Simulate hesitation before action (REDUCED - only 8% chance, shorter delays)
     */
    addHesitation(baseDelay: number): number {
        // Reduced from 15% to 8%, shorter hesitation
        if (Math.random() < 0.08) {
            return baseDelay + 150 + Math.random() * 400; // Reduced from 200-800ms
        }
        return baseDelay;
    }

    /**
     * Inject visibility API events (REDUCED - 3% chance instead of 8%)
     */
    async simulateTabSwitch(): Promise<void> {
        if (Math.random() < 0.03) { // Reduced from 8%
            try {
                await this.page.evaluate(() => {
                    window.dispatchEvent(new Event('blur'));
                });
                
                // Shorter "away" time: 500-2000ms instead of 1-4s
                await this.page.waitForTimeout(500 + Math.random() * 1500);
                
                await this.page.evaluate(() => {
                    window.dispatchEvent(new Event('focus'));
                });
            } catch (error) {
                // Silent
            }
        }
    }

    /**
     * Add natural touch events (REMOVED - too rare, not worth the overhead)
     */
    async injectTouchEvents(x: number, y: number): Promise<void> {
        // Disabled for speed - only 5% of users have touch anyway
        return;
    }

    /**
     * Get natural mouse button (SIMPLIFIED - 99% left click, 1% accidental)
     */
    getNaturalMouseButton(): number {
        return Math.random() < 0.99 ? 0 : 1; // 99% left, 1% middle
    }

    /**
     * Add natural key press timing variance (OPTIMIZED)
     * Uses rhythm correlation but keeps it fast
     */
    getKeyPressDelay(baseDelay: number, previousDelay: number): number {
        // Subtle flow factor (20% chance)
        const flowFactor = Math.random() < 0.2 ? 0.80 : 1.0;
        
        // Rare stumble (8% chance, reduced multiplier)
        const stumbleFactor = Math.random() < 0.08 ? 1.3 + Math.random() * 0.7 : 1.0;
        
        // Light correlation with previous delay
        const correlation = previousDelay > baseDelay * 1.3 ? 1.15 : 0.95;
        
        return baseDelay * flowFactor * stumbleFactor * correlation;
    }

    /**
     * Simulate cursor drift (REMOVED - too slow)
     */
    async addCursorDrift(x: number, y: number, duration: number): Promise<void> {
        // Disabled for speed - this was adding too much overhead
        return;
    }

    /**
     * Inject wheel events (FAST - synchronous, no await)
     */
    async injectWheelEvent(x: number, y: number, deltaY: number): Promise<void> {
        // Only inject 15% of the time for speed
        if (Math.random() > 0.15) return;
        
        try {
            await this.page.evaluate(({ x, y, deltaY }: { x: number; y: number; deltaY: number }) => {
                const el = document.elementFromPoint(x, y) || document.body;
                el.dispatchEvent(new WheelEvent('wheel', {
                    bubbles: true,
                    cancelable: true,
                    clientX: x,
                    clientY: y,
                    deltaY: deltaY,
                    deltaMode: 0
                }));
            }, { x, y, deltaY });
        } catch (error) {
            // Silent
        }
    }

    /**
     * SMART TIMING: Variable delays that break patterns without being slow
     * Key insight: Variance in RELATIVE timing matters more than absolute time
     */
    getSmartDelay(baseMs: number, category: 'hover' | 'click' | 'scroll' | 'type'): number {
        // Different variance profiles for different actions
        // Wider variance profiles to make per-action timing less predictable
        const profiles = {
            hover: { min: 0.6, max: 1.6 },    // 60-160% of base
            click: { min: 0.7, max: 1.5 },    // 70-150% of base
            scroll: { min: 0.5, max: 1.8 },   // 50-180% of base
            type: { min: 0.4, max: 2.5 }      // 40-250% of base
        };

        const profile = profiles[category];
        const multiplier = profile.min + Math.random() * (profile.max - profile.min);

        // Increased chance of micro-spike to create occasional outliers (12% chance)
        if (Math.random() < 0.12) {
            return Math.floor(baseMs * multiplier * (1.4 + Math.random() * 1.2)); // 1.4-2.6x
        }

        return Math.floor(baseMs * multiplier);
    }

    /**
     * PATTERN BREAKER: Add session-level variance to timing
     * Each session has slightly different "tempo" - this is the key to beating 20-25 threshold
     */
    getSessionTempoMultiplier(): number {
        // Generate once per session, store in cache
        if (!this.eventCache.has('sessionTempo')) {
            // 70-130% base tempo for this entire session
            const tempo = 0.7 + Math.random() * 0.6;
            this.eventCache.set('sessionTempo', tempo);
        }
        return this.eventCache.get('sessionTempo')!;
    }

    /**
     * CRITICAL: Simulate mouse leaving viewport
     * Real users move mouse outside window - bots never do
     */
    async simulateMouseLeave(duration: number): Promise<void> {
        try {
            await this.page.evaluate(() => {
                // Dispatch mouseleave event on document
                document.dispatchEvent(new MouseEvent('mouseleave', {
                    bubbles: true,
                    cancelable: true
                }));
                
                // Dispatch mouseout on body
                document.body.dispatchEvent(new MouseEvent('mouseout', {
                    bubbles: true,
                    cancelable: true
                }));
            });
            
            // Simulate being away
            await this.page.waitForTimeout(duration);
            
            // Mouse returns to viewport
            await this.page.evaluate(() => {
                document.dispatchEvent(new MouseEvent('mouseenter', {
                    bubbles: true,
                    cancelable: true
                }));
            });
        } catch (error) {
            // Silent
        }
    }

    /**
     * CRITICAL: Simulate browser focus loss (tab switch, minimize, etc.)
     * Akamai tracks visibility API - bots never lose focus
     */
    async simulateFocusLoss(duration: number): Promise<void> {
        try {
            // Lose focus
            await this.page.evaluate(() => {
                // Visibility API events
                Object.defineProperty(document, 'hidden', {
                    writable: true,
                    configurable: true,
                    value: true
                });
                document.dispatchEvent(new Event('visibilitychange'));
                
                // Focus/blur events
                window.dispatchEvent(new Event('blur'));
                document.dispatchEvent(new Event('blur'));
            });
            
            // User is away (checking phone, other tab, etc.)
            await this.page.waitForTimeout(duration);
            
            // Regain focus
            await this.page.evaluate(() => {
                Object.defineProperty(document, 'hidden', {
                    writable: true,
                    configurable: true,
                    value: false
                });
                document.dispatchEvent(new Event('visibilitychange'));
                
                window.dispatchEvent(new Event('focus'));
                document.dispatchEvent(new Event('focus'));
            });
        } catch (error) {
            // Silent
        }
    }

    /**
     * CRITICAL: Simulate paste event (from clipboard)
     * Some users paste from password managers - bots always type
     * INCLUDES CTRL+V KEYBOARD EVENT - Akamai tracks this!
     */
    async simulatePaste(element: any, text: string): Promise<void> {
        try {
            console.log(`🔄 Attempting to paste value: "${text}"`);
            
            // CRITICAL: Simulate Ctrl+V keyboard events BEFORE paste
            // Akamai detects paste without keyboard event = bot
            await this.page.keyboard.down('Control');
            await this.page.keyboard.press('v');
            await this.page.keyboard.up('Control');
            
            // Small delay between keyboard and paste (realistic)
            await this.page.waitForTimeout(20 + Math.random() * 30);
            
            await element.evaluate((el: HTMLInputElement, value: string) => {
                // Focus the element first
                el.focus();
                
                // Clear existing value first
                el.value = '';
                
                // Create and dispatch paste event BEFORE setting value
                const pasteEvent = new ClipboardEvent('paste', {
                    bubbles: true,
                    cancelable: true,
                    clipboardData: new DataTransfer()
                });
                
                // Set clipboard data
                pasteEvent.clipboardData?.setData('text/plain', value);
                
                // Dispatch paste event
                el.dispatchEvent(pasteEvent);
                
                // Set value (simulating paste) - use multiple methods for compatibility
                el.value = value;
                
                // Also set attribute for frameworks that watch attributes
                el.setAttribute('value', value);
                
                // Trigger input event first (before change)
                const inputEvent = new Event('input', { bubbles: true });
                el.dispatchEvent(inputEvent);
                
                // Also set property directly (for some frameworks)
                Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(el, value);
                
                // Trigger another input event after property set
                el.dispatchEvent(new Event('input', { bubbles: true }));
                
                // Trigger change event
                const changeEvent = new Event('change', { bubbles: true });
                el.dispatchEvent(changeEvent);
                
                // Trigger keyup event (some forms listen to this)
                const keyupEvent = new KeyboardEvent('keyup', { bubbles: true });
                el.dispatchEvent(keyupEvent);
                
                // DON'T dispatch blur - keeps field focused
            }, text);
            
            // Wait longer for events to propagate and frameworks to react
            await this.page.waitForTimeout(250 + Math.random() * 150);
            
            // Verify the value was actually set
            const actualValue = await element.evaluate((el: HTMLInputElement) => el.value);
            
            if (actualValue !== text) {
                throw new Error(`Paste verification failed: expected "${text}", got "${actualValue}"`);
            }
            
            console.log(`✅ Successfully pasted and verified: "${text}"`);
        } catch (error) {
            console.error(`❌ Paste simulation failed: ${error}`);
            // Re-throw error so caller knows paste failed
            throw new Error(`Paste simulation failed: ${error}`);
        }
    }

    /**
     * CRITICAL: Simulate right-click context menu
     * Real users accidentally right-click sometimes
     */
    async simulateRightClick(x: number, y: number): Promise<void> {
        try {
            await this.page.evaluate(({ x, y }: { x: number; y: number }) => {
                const el = document.elementFromPoint(x, y);
                if (el) {
                    el.dispatchEvent(new MouseEvent('contextmenu', {
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y,
                        button: 2 // Right button
                    }));
                }
            }, { x, y });
            
            // Immediately close context menu (user realizes mistake)
            await this.page.keyboard.press('Escape');
        } catch (error) {
            // Silent
        }
    }

    /**
     * CRITICAL: Apply mouse acceleration
     * Real mouse movements accelerate/decelerate naturally
     * Bots have constant velocity - instant detection
     */
    applyMouseAcceleration(baseDelay: number, progress: number, accelerations: number[]): number {
        if (accelerations.length === 0) return baseDelay;
        
        // Get acceleration for current progress point
        const index = Math.floor(progress * (accelerations.length - 1));
        const acceleration = accelerations[Math.min(index, accelerations.length - 1)];
        
        // Apply acceleration to delay (inverse: faster = shorter delay)
        return baseDelay / acceleration;
    }

    /**
     * CRITICAL: Get digraph typing speed
     * Humans type common letter pairs faster
     */
    getDigraphDelay(prev: string, current: string, baseDelay: number, rhythmMap: Map<string, number>): number {
        const digraph = (prev + current).toLowerCase();
        
        if (rhythmMap.has(digraph)) {
            return baseDelay * rhythmMap.get(digraph)!;
        }
        
        // Also check individual letter frequency (common letters typed faster)
        const commonLetters = 'etaoinshrdlu'; // Most common in English
        if (commonLetters.includes(current.toLowerCase())) {
            return baseDelay * (0.85 + Math.random() * 0.2); // 85-105% speed
        }
        
        return baseDelay;
    }

    /**
     * CRITICAL: Randomize form field event sequences
     * Prevents Akamai from detecting identical event patterns
     * Real users don't always fire events in the same order
     */
    async dispatchFieldEventsRealistically(field: any): Promise<void> {
        try {
            // 4 different realistic event sequences
            const sequences = [
                // Sequence 1: Normal flow (45% probability)
                async () => {
                    await field.dispatchEvent('input');
                    await this.page.waitForTimeout(10 + Math.random() * 90);
                    await field.dispatchEvent('change');
                    await this.page.waitForTimeout(5 + Math.random() * 50);
                    await field.dispatchEvent('blur');
                },
                // Sequence 2: Fast user (25% probability)
                async () => {
                    await field.dispatchEvent('input');
                    await field.dispatchEvent('change');
                    await this.page.waitForTimeout(3 + Math.random() * 15);
                    await field.dispatchEvent('blur');
                },
                // Sequence 3: User pauses mid-input (20% probability)
                async () => {
                    await field.dispatchEvent('input');
                    await this.page.waitForTimeout(200 + Math.random() * 800);
                    await field.dispatchEvent('input'); // Duplicate is natural
                    await this.page.waitForTimeout(20 + Math.random() * 100);
                    await field.dispatchEvent('change');
                    await field.dispatchEvent('blur');
                },
                // Sequence 4: Skip change event (10% probability - happens in real browsers)
                async () => {
                    await field.dispatchEvent('input');
                    await this.page.waitForTimeout(30 + Math.random() * 120);
                    await field.dispatchEvent('blur');
                }
            ];
            
            // Weighted random selection
            const roll = Math.random();
            let chosenSequence;
            
            if (roll < 0.45) {
                chosenSequence = sequences[0];
            } else if (roll < 0.70) {
                chosenSequence = sequences[1];
            } else if (roll < 0.90) {
                chosenSequence = sequences[2];
            } else {
                chosenSequence = sequences[3];
            }
            
            await chosenSequence();
        } catch (error) {
            // Silent - fallback to basic events
            try {
                await field.dispatchEvent('input');
                await field.dispatchEvent('change');
                await field.dispatchEvent('blur');
            } catch (e) {
                // Complete silent fail
            }
        }
    }

    /**
     * CRITICAL: Fire beforeinput event before typing
     * Akamai detects input without beforeinput = bot
     */
    async injectBeforeInputEvent(element: any, char: string): Promise<void> {
        try {
            await element.evaluate((el: HTMLInputElement, char: string) => {
                el.dispatchEvent(new InputEvent('beforeinput', {
                    bubbles: true,
                    cancelable: true,
                    data: char,
                    inputType: 'insertText',
                    composed: true
                }));
            }, char);
        } catch (error) {
            // Silent
        }
    }

    /**
     * CRITICAL: Fire proper input event with inputType
     */
    async injectInputEvent(element: any): Promise<void> {
        try {
            await element.evaluate((el: HTMLInputElement) => {
                el.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    cancelable: false,
                    inputType: 'insertText',
                    composed: true
                }));
            });
        } catch (error) {
            // Silent
        }
    }

    /**
     * CRITICAL: Randomly fire touch events (capacitive screens/trackpads)
     * 5% of interactions should have touch events even on desktop
     */
    async maybeInjectTouchEvents(x: number, y: number): Promise<void> {
        try {
            // Only 5% of the time
            if (Math.random() > 0.05) return;
            
            await this.page.evaluate(({ x, y }: { x: number; y: number }) => {
                const el = document.elementFromPoint(x, y);
                if (el) {
                    // TouchStart
                    el.dispatchEvent(new TouchEvent('touchstart', {
                        bubbles: true,
                        cancelable: true,
                        composed: true,
                        touches: [{
                            identifier: 0,
                            target: el,
                            clientX: x,
                            clientY: y,
                            pageX: x,
                            pageY: y,
                            screenX: x,
                            screenY: y,
                            radiusX: 10,
                            radiusY: 10,
                            rotationAngle: 0,
                            force: 1
                        }] as any
                    }));
                    
                    // TouchEnd after short delay
                    setTimeout(() => {
                        el.dispatchEvent(new TouchEvent('touchend', {
                            bubbles: true,
                            cancelable: true,
                            composed: true
                        }));
                    }, 20 + Math.random() * 80);
                }
            }, { x, y });
        } catch (error) {
            // Silent
        }
    }

    /**
     * CRITICAL: Network-aware delays
     * Real users slow down when page is loading
     */
    async getNetworkAwareDelay(baseDelay: number): Promise<number> {
        try {
            // Check if page is still loading resources
            const isLoading = await this.page.evaluate(() => {
                return document.readyState !== 'complete' || 
                       performance.getEntriesByType('resource').some(r => 
                           (r as PerformanceResourceTiming).responseEnd === 0
                       );
            });
            
            if (isLoading) {
                // User waits a bit longer when they see loading
                return baseDelay * (1.2 + Math.random() * 0.5); // 120-170% delay
            }
        } catch (error) {
            // Silent
        }
        
        return baseDelay;
    }
}
