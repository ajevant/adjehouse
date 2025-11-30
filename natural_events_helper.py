"""
Natural Events Helper - Python implementation of TypeScript NaturalEvents
Provides realistic browser events to bypass Cloudflare/Akamai detection
Based on fifa-entry-mailserver-imap/helpers/naturalEvents.ts
"""

import random
import time
from typing import Optional, Tuple


class NaturalEventsHelper:
    """
    Helper class for injecting natural browser events to evade bot detection
    Optimized for Selenium WebDriver
    """
    
    def __init__(self, driver):
        self.driver = driver
        self.event_cache = {}  # Cache for session-level data
    
    def inject_focus_events(self, element) -> bool:
        """
        CRITICAL: Inject natural focus/blur event sequence with parent events
        Akamai tracks focusin on parents + pointerenter
        """
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                if (!el) return false;
                
                // CRITICAL: Fire focusin on parent FIRST (bubbles up)
                var parent = el.parentElement;
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
                
                return true;
            """, element)
            return True
        except Exception:
            return False
    
    def inject_before_input_event(self, element, char: str) -> bool:
        """
        CRITICAL: Fire beforeinput event before typing
        Akamai detects input without beforeinput = bot
        """
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                var char = arguments[1];
                if (!el) return false;
                
                el.dispatchEvent(new InputEvent('beforeinput', {
                    bubbles: true,
                    cancelable: true,
                    data: char,
                    inputType: 'insertText',
                    composed: true
                }));
                
                return true;
            """, element, char)
            return True
        except Exception:
            return False
    
    def inject_input_event(self, element) -> bool:
        """
        CRITICAL: Fire proper input event with inputType
        """
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                if (!el) return false;
                
                el.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    cancelable: false,
                    inputType: 'insertText',
                    composed: true
                }));
                
                return true;
            """, element)
            return True
        except Exception:
            return False
    
    def inject_pointer_events(self, x: int, y: int, event_type: str = 'move') -> bool:
        """
        Inject natural pointer events (FAST - 10% of the time)
        """
        # Only inject 10% of the time for speed
        if random.random() > 0.1:
            return False
        
        try:
            self.driver.execute_script("""
                var x = arguments[0];
                var y = arguments[1];
                var type = arguments[2];
                
                var el = document.elementFromPoint(x, y);
                if (el) {
                    var eventName = 'pointer' + type;
                    el.dispatchEvent(new PointerEvent(eventName, {
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y,
                        pointerId: 1,
                        pointerType: 'mouse',
                        isPrimary: true
                    }));
                }
            """, x, y, event_type)
            return True
        except Exception:
            return False
    
    def simulate_paste(self, element, text: str) -> bool:
        """
        CRITICAL: Simulate paste event (from clipboard)
        Some users paste from password managers - bots always type
        INCLUDES CTRL+V KEYBOARD EVENT - Akamai tracks this!
        """
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains
            
            # CRITICAL: Simulate Ctrl+V keyboard events BEFORE paste
            # Akamai detects paste without keyboard event = bot
            actions = ActionChains(self.driver)
            actions.key_down(Keys.CONTROL)
            actions.send_keys('v')
            actions.key_up(Keys.CONTROL)
            actions.perform()
            
            # Small delay between keyboard and paste (realistic)
            time.sleep(random.uniform(0.02, 0.05))
            
            # Execute paste via JavaScript
            self.driver.execute_script("""
                var el = arguments[0];
                var value = arguments[1];
                if (!el) return false;
                
                // Focus the element first
                el.focus();
                
                // Clear existing value first
                el.value = '';
                
                // Create and dispatch paste event BEFORE setting value
                var pasteEvent = new ClipboardEvent('paste', {
                    bubbles: true,
                    cancelable: true,
                    clipboardData: new DataTransfer()
                });
                
                // Set clipboard data
                if (pasteEvent.clipboardData) {
                    pasteEvent.clipboardData.setData('text/plain', value);
                }
                
                // Dispatch paste event
                el.dispatchEvent(pasteEvent);
                
                // Set value (simulating paste) - use multiple methods for compatibility
                el.value = value;
                
                // Also set attribute for frameworks that watch attributes
                el.setAttribute('value', value);
                
                // Trigger input event first (before change)
                var inputEvent = new Event('input', { bubbles: true });
                el.dispatchEvent(inputEvent);
                
                // Also set property directly (for some frameworks)
                var descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                if (descriptor && descriptor.set) {
                    descriptor.set.call(el, value);
                }
                
                // Trigger another input event after property set
                el.dispatchEvent(new Event('input', { bubbles: true }));
                
                // Trigger change event
                var changeEvent = new Event('change', { bubbles: true });
                el.dispatchEvent(changeEvent);
                
                // Trigger keyup event (some forms listen to this)
                var keyupEvent = new KeyboardEvent('keyup', { bubbles: true });
                el.dispatchEvent(keyupEvent);
                
                return true;
            """, element, text)
            
            # Wait longer for events to propagate and frameworks to react
            time.sleep(random.uniform(0.25, 0.4))
            
            # Verify the value was actually set
            actual_value = element.get_attribute('value')
            if actual_value != text:
                # Try setting directly as fallback
                element.clear()
                element.send_keys(text)
                return True
            
            return True
        except Exception as e:
            # Fallback to direct send_keys
            try:
                element.clear()
                element.send_keys(text)
                return True
            except:
                return False
    
    def simulate_mouse_leave(self, duration_ms: int = 500) -> bool:
        """
        CRITICAL: Simulate mouse leaving viewport
        Real users move mouse outside window - bots never do
        """
        try:
            self.driver.execute_script("""
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
            """)
            
            # Simulate being away
            time.sleep(duration_ms / 1000.0)
            
            # Mouse returns to viewport
            self.driver.execute_script("""
                document.dispatchEvent(new MouseEvent('mouseenter', {
                    bubbles: true,
                    cancelable: true
                }));
            """)
            return True
        except Exception:
            return False
    
    def simulate_focus_loss(self, duration_ms: int = 1000) -> bool:
        """
        CRITICAL: Simulate browser focus loss (tab switch, minimize, etc.)
        Akamai tracks visibility API - bots never lose focus
        """
        try:
            # Lose focus
            self.driver.execute_script("""
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
            """)
            
            # User is away (checking phone, other tab, etc.)
            time.sleep(duration_ms / 1000.0)
            
            # Regain focus
            self.driver.execute_script("""
                Object.defineProperty(document, 'hidden', {
                    writable: true,
                    configurable: true,
                    value: false
                });
                document.dispatchEvent(new Event('visibilitychange'));
                
                window.dispatchEvent(new Event('focus'));
                document.dispatchEvent(new Event('focus'));
            """)
            return True
        except Exception:
            return False
    
    def get_smart_delay(self, base_ms: float, category: str = 'click') -> float:
        """
        SMART TIMING: Variable delays that break patterns without being slow
        Key insight: Variance in RELATIVE timing matters more than absolute time
        """
        # Different variance profiles for different actions
        profiles = {
            'hover': {'min': 0.6, 'max': 1.6},    # 60-160% of base
            'click': {'min': 0.7, 'max': 1.5},    # 70-150% of base
            'scroll': {'min': 0.5, 'max': 1.8},   # 50-180% of base
            'type': {'min': 0.4, 'max': 2.5}      # 40-250% of base
        }
        
        profile = profiles.get(category, profiles['click'])
        multiplier = profile['min'] + random.random() * (profile['max'] - profile['min'])
        
        # Increased chance of micro-spike to create occasional outliers (12% chance)
        if random.random() < 0.12:
            return base_ms * multiplier * (1.4 + random.random() * 1.2)  # 1.4-2.6x
        
        return base_ms * multiplier
    
    def get_session_tempo_multiplier(self) -> float:
        """
        PATTERN BREAKER: Add session-level variance to timing
        Each session has slightly different "tempo" - this is the key to beating detection
        """
        # Generate once per session, store in cache
        if 'sessionTempo' not in self.event_cache:
            # 70-130% base tempo for this entire session
            tempo = 0.7 + random.random() * 0.6
            self.event_cache['sessionTempo'] = tempo
        
        return self.event_cache['sessionTempo']
    
    def dispatch_field_events_realistically(self, element) -> bool:
        """
        CRITICAL: Randomize form field event sequences
        Prevents Akamai from detecting identical event patterns
        Real users don't always fire events in the same order
        """
        try:
            # 4 different realistic event sequences
            roll = random.random()
            
            if roll < 0.45:
                # Sequence 1: Normal flow (45% probability)
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                """, element)
                time.sleep(random.uniform(0.01, 0.1))
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                """, element)
                time.sleep(random.uniform(0.005, 0.05))
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, element)
            elif roll < 0.70:
                # Sequence 2: Fast user (25% probability)
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                """, element)
                time.sleep(random.uniform(0.003, 0.018))
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, element)
            elif roll < 0.90:
                # Sequence 3: User pauses mid-input (20% probability)
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                """, element)
                time.sleep(random.uniform(0.2, 0.8))
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('input', { bubbles: true })); // Duplicate is natural
                """, element)
                time.sleep(random.uniform(0.02, 0.1))
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, element)
            else:
                # Sequence 4: Skip change event (10% probability - happens in real browsers)
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                """, element)
                time.sleep(random.uniform(0.03, 0.12))
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, element)
            
            return True
        except Exception:
            # Fallback to basic events
            try:
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, element)
                return True
            except:
                return False
    
    def maybe_inject_touch_events(self, x: int, y: int) -> bool:
        """
        CRITICAL: Randomly fire touch events (capacitive screens/trackpads)
        5% of interactions should have touch events even on desktop
        """
        # Only 5% of the time
        if random.random() > 0.05:
            return False
        
        try:
            self.driver.execute_script("""
                var x = arguments[0];
                var y = arguments[1];
                
                var el = document.elementFromPoint(x, y);
                if (el) {
                    // TouchStart
                    var touch = {
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
                    };
                    
                    el.dispatchEvent(new TouchEvent('touchstart', {
                        bubbles: true,
                        cancelable: true,
                        composed: true,
                        touches: [touch],
                        targetTouches: [touch],
                        changedTouches: [touch]
                    }));
                    
                    // TouchEnd after short delay
                    setTimeout(function() {
                        el.dispatchEvent(new TouchEvent('touchend', {
                            bubbles: true,
                            cancelable: true,
                            composed: true,
                            touches: [],
                            targetTouches: [],
                            changedTouches: [touch]
                        }));
                    }, 20 + Math.random() * 80);
                }
            """, x, y)
            return True
        except Exception:
            return False


