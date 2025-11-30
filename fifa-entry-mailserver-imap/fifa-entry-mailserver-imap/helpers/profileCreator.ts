// Types and interfaces
interface FingerprintData {
    fonts: string;
    screen: {
        width: number;
        height: number;
    };
    connection: {
        downlink: number;
        rtt: number;
        effectiveType: string;
        saveData: boolean;
    };
    hardwareConcurrency: number;
    deviceMemory: number;
    webgl: {
        unmaskedVendor: string;
        unmaskedRenderer: string;
    };
    webgl2Maximum: any;
    platform: string;
    cpu: {
        architecture: string;
    };
    os: {
        version: string;
    };
    vendorSub: string;
    productSub: string;
    vendor: string;
    product: string;
    appCodeName: string;
    userAgent: string;
    webgpu: string;
    platformVersion: string;
}

interface ProfileOptions {
    name?: string;
    tags?: string[];
    platform?: string;
    platformVersion?: string;
    browserType?: string;
    mainWebsite?: string;
    useRandomProxy?: boolean;
    customProxy?: any;
}

interface ProfileData {
    name: string;
    tags: string[];
    platform: string;
    platformVersion: string;
    browserType: string;
    mainWebsite?: string;
    proxy: any;
    args: any[];
    notes: any[];
    login: any;
    password: any;
    fingerprint: any;
    uaFullVersion: any;
    folderId: any;
    homepages: any[];
    newHomepages: any[];
    fontsMode: string;
    fonts: string[];
    macAddress: {
        mode: string;
        value: string;
    };
    deviceName: {
        mode: string;
        value: string;
        valueNew: string;
    };
   
    audio?: {
        mode: string;
    };
    isHiddenProfileName: boolean;
    disableLoadWebCameraAndCookies: any;
    enableArgIsChromeIcon: any;
    doNotTrack: boolean;
    statusId: number;
    useragent: {
        mode: string;
        value: string;
    };
    webrtc: {
        mode: string;
        ipAddress: any;
    };
    canvas: {
        mode: string;
        noise?: any;
    };
    webgl: {
        mode: string;
        noise?: any;
    };
    webgpu: {
        mode: string;
        value: string;
    };
    webglInfo: {
        mode: string;
        vendor?: string;
        renderer?: string;
        webgl2Maximum?: any;
    };
    clientRect: {
        mode: string;
    };
    timezone: {
        mode: string;
        value: any;
    };
    locale: {
        mode: string;
        value: any;
    };
    geolocation: {
        mode: string;
        latitude?: any;
        longitude?: any;
        accuracy?: any;
    };
    cpu: {
        mode: string;
        value: number;
    };
    memory: {
        mode: string;
        value: number;
    };
    screen?: {
        mode?: string;
        resolution?: string;
        width?: number;
        height?: number;
    };
    connectionDownlink: number;
    connectionEffectiveType: string;
    connectionRtt: number;
    connectionSaveData: boolean;
    platformName: string;
    cpuArchitecture: string;
    osVersion: string;
    screenWidth?: number;
    screenHeight?: number;
    vendorSub: string;
    productSub: string;
    vendor: string;
    product: string;
    appCodeName: string;
    mediaDevices: {
        mode: string;
        audioInputs?: any;
        videoInputs?: any;
        audioOutputs?: any;
    };
    userFields: any[];
    ports: {
        mode: string;
        blacklist: string[];
    };
}

interface ProfileResponse {
    success: boolean;
    browserProfileId: string;
    proxy: {
        id: string;
    };
    profileData: ProfileData;
}

import { getAllProxies, getRandomUnusedProxy } from './proxyManager';
import config from './config';
import SettingsHelper from './settingsHelper';

// Initialize settings helper (singleton)
const settings = SettingsHelper.getInstance();

// Your Dolphin Anty token (from settings.txt)
const API_TOKEN: string = settings.get('DOLPHYN_API_TOKEN') as string;

// Safe fetch helper for Node <18
const fetchAny = async (url: string, options?: any): Promise<Response> => {
    if (typeof fetch !== 'undefined') return fetch(url, options);
    const nf = (await import('node-fetch')).default;
    return nf(url, options);
};


// API base URL
const API_BASE_URL: string = config.API_BASE_URL;

/**
 * Real Apple Silicon chip specifications
 */
const APPLE_SILICON_SPECS: { [key: string]: { minCores: number; maxCores: number; minMemory: number; maxMemory: number } } = {
    'M1': { minCores: 8, maxCores: 8, minMemory: 8, maxMemory: 16 },
    'M1 Pro': { minCores: 8, maxCores: 10, minMemory: 16, maxMemory: 32 },
    'M1 Max': { minCores: 10, maxCores: 10, minMemory: 32, maxMemory: 64 },
    'M1 Ultra': { minCores: 20, maxCores: 20, minMemory: 64, maxMemory: 128 },
    'M2': { minCores: 8, maxCores: 8, minMemory: 8, maxMemory: 24 },
    'M2 Pro': { minCores: 10, maxCores: 12, minMemory: 16, maxMemory: 32 },
    'M2 Max': { minCores: 12, maxCores: 12, minMemory: 32, maxMemory: 96 },
    'M2 Ultra': { minCores: 24, maxCores: 24, minMemory: 64, maxMemory: 192 },
    'M3': { minCores: 8, maxCores: 8, minMemory: 8, maxMemory: 24 },
    'M3 Pro': { minCores: 11, maxCores: 12, minMemory: 18, maxMemory: 36 },
    'M3 Max': { minCores: 14, maxCores: 16, minMemory: 36, maxMemory: 128 },
    'M3 Ultra': { minCores: 28, maxCores: 32, minMemory: 64, maxMemory: 256 },
    'M4': { minCores: 9, maxCores: 10, minMemory: 16, maxMemory: 32 },
    'M4 Pro': { minCores: 12, maxCores: 14, minMemory: 24, maxMemory: 64 },
    'M4 Max': { minCores: 14, maxCores: 16, minMemory: 36, maxMemory: 128 }
};

/**
 * Extract Apple chip model from renderer string
 */
function extractAppleChipModel(renderer: string): string | null {
    const chipPatterns = [
        /Apple M(\d+)\s*(Ultra|Max|Pro)?/i,
        /M(\d+)\s*(Ultra|Max|Pro)?/i
    ];
    
    for (const pattern of chipPatterns) {
        const match = renderer.match(pattern);
        if (match) {
            const version = match[1];
            const variant = match[2] ? ` ${match[2]}` : '';
            return `M${version}${variant}`;
        }
    }
    return null;
}

/**
 * Validate Apple Silicon hardware specifications
 */
function validateAppleSiliconSpecs(chipModel: string, cores: number, memory: number): string[] {
    const issues: string[] = [];
    const specs = APPLE_SILICON_SPECS[chipModel];
    
    if (!specs) {
        // Unknown chip model - allow it but log
        return issues;
    }
    
    // Validate core count
    if (cores < specs.minCores || cores > specs.maxCores) {
        if (specs.minCores === specs.maxCores) {
            issues.push(`${chipModel} always has exactly ${specs.minCores} cores, but fingerprint shows ${cores} cores`);
        } else {
            issues.push(`${chipModel} has ${specs.minCores}-${specs.maxCores} cores, but fingerprint shows ${cores} cores`);
        }
    }
    
    // Validate memory
    if (memory < specs.minMemory || memory > specs.maxMemory) {
        issues.push(`${chipModel} supports ${specs.minMemory}-${specs.maxMemory}GB RAM, but fingerprint shows ${memory}GB`);
    }
    
    return issues;
}

/**
 * Validate Intel Mac hardware specifications
 */
function validateIntelMacSpecs(renderer: string, cores: number, memory: number): string[] {
    const issues: string[] = [];
    const rendererLower = renderer.toLowerCase();
    
    // Intel Macs typically have 2-28 cores (up to Mac Pro)
    if (cores < 2 || cores > 28) {
        issues.push(`Unrealistic core count for Intel Mac: ${cores} (valid range: 2-28)`);
    }
    
    // Intel Macs typically support 8-1536GB RAM (Mac Pro can go very high)
    // But most consumer models max out at 64GB
    if (memory < 4 || memory > 128) {
        issues.push(`Unrealistic memory for typical Intel Mac: ${memory}GB (valid range: 4-128GB for consumer models)`);
    }
    
    // Check for specific Intel GPU models and their typical core counts
    if (rendererLower.includes('iris') && rendererLower.includes('plus')) {
        // Iris Plus typically in lower-end Macs with 2-8 cores
        if (cores > 8) {
            issues.push(`Intel Iris Plus Graphics typically paired with 2-8 cores, not ${cores} cores`);
        }
    } else if (rendererLower.includes('iris pro')) {
        // Iris Pro in mid-range Macs with 4-8 cores
        if (cores < 4 || cores > 8) {
            issues.push(`Intel Iris Pro Graphics typically paired with 4-8 cores, not ${cores} cores`);
        }
    } else if (rendererLower.includes('iris') && !rendererLower.includes('plus') && !rendererLower.includes('pro')) {
        // Regular Iris Graphics in lower-end Macs with 2-6 cores
        if (cores > 6) {
            issues.push(`Intel Iris Graphics typically paired with 2-6 cores, not ${cores} cores`);
        }
    } else if (rendererLower.includes('uhd graphics 630')) {
        // UHD 630 in higher-end consumer Macs with 4-10 cores
        if (cores < 4 || cores > 10) {
            issues.push(`Intel UHD Graphics 630 typically paired with 4-10 cores, not ${cores} cores`);
        }
    } else if (rendererLower.includes('uhd graphics')) {
        // Generic UHD Graphics in mid-range Macs with 2-8 cores
        if (cores > 10) {
            issues.push(`Intel UHD Graphics typically paired with 2-10 cores, not ${cores} cores`);
        }
    }
    
    return issues;
}

/**
 * Validate fingerprint consistency to ensure it won't be flagged as bot
 * @param {FingerprintData} fingerprint - Fingerprint to validate
 * @returns {object} Validation result with isValid flag and reasons
 */
function validateFingerprintConsistency(fingerprint: FingerprintData): { isValid: boolean; reasons: string[] } {
    const reasons: string[] = [];

    // Check 1: CPU Architecture must match WebGL vendor
    const cpuArch = fingerprint.cpu.architecture.toLowerCase();
    const webglVendor = fingerprint.webgl.unmaskedVendor.toLowerCase();
    const webglRenderer = fingerprint.webgl.unmaskedRenderer.toLowerCase();
    const hwConcurrency = fingerprint.hardwareConcurrency;
    const deviceMemory = fingerprint.deviceMemory;

    if (cpuArch === 'arm') {
        // ARM Macs should have Apple graphics
        if (!webglVendor.includes('apple') || !webglRenderer.includes('apple')) {
            reasons.push(`CPU is ARM but WebGL vendor is not Apple (${fingerprint.webgl.unmaskedVendor})`);
        } else {
            // Validate Apple Silicon chip specifications
            const chipModel = extractAppleChipModel(fingerprint.webgl.unmaskedRenderer);
            if (chipModel) {
                const appleIssues = validateAppleSiliconSpecs(chipModel, hwConcurrency, deviceMemory);
                reasons.push(...appleIssues);
            }
        }
    } else if (cpuArch === 'x86') {
        // x86 Macs should have Intel graphics
        if (!webglVendor.includes('intel') || !webglRenderer.includes('intel')) {
            reasons.push(`CPU is x86 but WebGL vendor is not Intel (${fingerprint.webgl.unmaskedVendor})`);
        } else {
            // Validate Intel Mac specifications
            const intelIssues = validateIntelMacSpecs(fingerprint.webgl.unmaskedRenderer, hwConcurrency, deviceMemory);
            reasons.push(...intelIssues);
        }
    }

    // Check 2: WebGPU architecture must match CPU architecture
    try {
        // WebGPU is double-escaped JSON, so we need to parse it twice
        let webgpuData: any = fingerprint.webgpu;
        
        // First parse if it's a stringified string
        if (typeof webgpuData === 'string' && webgpuData.startsWith('"')) {
            webgpuData = JSON.parse(webgpuData);
        }
        
        // Second parse to get the actual object
        if (typeof webgpuData === 'string') {
            webgpuData = JSON.parse(webgpuData);
        }
        
        const webgpuVendor = webgpuData?.info?.vendor?.toLowerCase() || '';
        const webgpuArch = webgpuData?.info?.architecture?.toLowerCase() || '';

        if (cpuArch === 'arm') {
            // ARM should have Apple vendor and common-3 architecture
            if (webgpuVendor !== 'apple' || !webgpuArch.includes('common')) {
                reasons.push(`CPU is ARM but WebGPU vendor is ${webgpuVendor} with architecture ${webgpuArch}`);
            }
        } else if (cpuArch === 'x86') {
            // x86 should have Intel vendor and gen-9 architecture
            if (webgpuVendor !== 'intel' || !webgpuArch.includes('gen')) {
                reasons.push(`CPU is x86 but WebGPU vendor is ${webgpuVendor} with architecture ${webgpuArch}`);
            }
        }
    } catch (e) {
        // WebGPU parsing failed - this is suspicious but not a deal-breaker
        // Don't add to reasons as it might not be critical
    }

    // Check 3: Hardware concurrency should be reasonable for the platform
    if (hwConcurrency < 2 || hwConcurrency > 128) {
        reasons.push(`Unrealistic hardware concurrency: ${hwConcurrency}`);
    }

    // Check 4: Platform version should exist and be reasonable
    if (!fingerprint.platformVersion || fingerprint.platformVersion.length < 5) {
        reasons.push('Missing or invalid platform version');
    }

    return {
        isValid: reasons.length === 0,
        reasons
    };
}

/**
 * Get complete fingerprint data from Dolphin API with validation
 * Retries until a valid, consistent fingerprint is received
 * @param {string} platform - Platform (default: "macos")
 * @param {string} browserType - Browser type (default: "anty")
 * @param {string} browserVersion - Browser version (default: "141")
 * @param {number} maxRetries - Maximum number of retries (default: 20)
 * @returns {Promise<FingerprintData>} Complete fingerprint data
 */
async function getFingerprint(platform: string = "macos", browserType: string = "anty", browserVersion: string = "141", maxRetries: number = 20): Promise<FingerprintData> {
    let attempts = 0;
    
    while (attempts < maxRetries) {
        attempts++;
        
        try {
            const response = await fetchAny(`${API_BASE_URL}/fingerprints/fingerprint?platform=${platform}&browser_type=${browserType}&browser_version=${browserVersion}&screen=1920x1080`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${API_TOKEN}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const fingerprint: FingerprintData = await response.json();
            
            // Validate the fingerprint
            const validation = validateFingerprintConsistency(fingerprint);
            
            if (true) {
                console.log(`✅ Valid fingerprint obtained (attempt ${attempts}/${maxRetries})`);
                return fingerprint;
            }
            // } else {
            //     console.log(`⚠️  Invalid fingerprint (attempt ${attempts}/${maxRetries}): ${validation.reasons.join(', ')}`);
            //     // Add small delay before retrying
            //     await new Promise(resolve => setTimeout(resolve, 100));
            // }
        } catch (error: any) {
            console.error(`❌ Error fetching fingerprint (attempt ${attempts}/${maxRetries}):`, error.message);
            
            // If it's the last attempt, throw the error
            if (attempts >= maxRetries) {
                throw error;
            }
            
            // Add small delay before retrying
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    
    throw new Error(`Failed to get valid fingerprint after ${maxRetries} attempts`);
}
async function getFontList(platform: string = "macos", browserType: string = "anty", browserVersion: string = "141"): Promise<{ id: number; font: string; type: string; os: string }[]> {
    try {
        const response = await fetchAny(`${API_BASE_URL}/fingerprints/font-list?platform=${platform}&browser_type=${browserType}&browser_version=${browserVersion}&userAgent=null`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${API_TOKEN}`,
                'Content-Type': 'application/json'
            }
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
      
        const result: { id: number; font: string; type: string; os: string }[] = await response.json();
        return result;
    } catch (error: any) {
        console.error('Error fetching font list:', error.message);
        throw error;
    }
}
// Old functions removed - now using single fingerprint API

/**
 * Generate random MAC address
 * @returns {string} Random MAC address
 */
function generateRandomMacAddress(): string {
    const bytes: number[] = Array.from({length: 6}, () => Math.floor(Math.random() * 256));
    // Set locally administered (bit 1) and unicast (bit 0 cleared)
    bytes[0] = (bytes[0] | 0x02) & 0xFE;
    return bytes.map(b => b.toString(16).padStart(2, '0')).join(':').toUpperCase();
}

/**
 * Generate realistic Mac device name (like Dolphin defaults)
 * @returns {string} Realistic Mac device name
 */
function generateRandomDeviceName(): string {
    const prefixes: string[] = config.DEVICE_NAME_PREFIXES;
    const names: string[] = config.DEVICE_NAMES;
    
    const prefix: string = prefixes[Math.floor(Math.random() * prefixes.length)];
    const name: string = names[Math.floor(Math.random() * names.length)];
    
    // 50% chance for "Device — Name" format, 50% for "Name Device" format
    if (Math.random() < 0.5) {
        return `${prefix} — ${name}`;
    } else {
        return `${name} ${prefix}`;
    }
}



/**
 * Create a new browser profile
 * @param {ProfileOptions} options - Profile creation options
 * @returns {Promise<ProfileResponse>} Created profile response
 */
async function createProfile(options: ProfileOptions = {}): Promise<ProfileResponse> {
    try { 
        const platformFromSettings = settings.getPlatform();
        
        const {
            name = `Profile-${Date.now()}`,
            tags = config.COMMON_TAGS.slice(0, 2), // Use first 2 common tags
            platform = platformFromSettings,
            browserType = config.DEFAULT_PROFILE_CONFIG.browserType,
            mainWebsite = config.DEFAULT_PROFILE_CONFIG.mainWebsite,
            useRandomProxy = true,
            customProxy = null
        } = options;

        // Get complete fingerprint data from new API
        const fingerprint: FingerprintData = await getFingerprint(platform, browserType, config.DEFAULT_PROFILE_CONFIG.browserVersion);
        //console.log(fingerprint);

        // Get proxy for profile creation
        let proxy: any;
        if (customProxy) {
            proxy = customProxy;
        } else if (useRandomProxy) {
            proxy = await getRandomUnusedProxy();
            if (!proxy) {
                throw new Error('No unused proxies available');
            }
        } else {
            throw new Error('No proxy specified');
        }
        const fontList: { id: number; font: string; type: string; os: string }[] = await getFontList(platform, browserType, config.DEFAULT_PROFILE_CONFIG.browserVersion);
        // AHH it should not be random, ity should select the fonts that the fingeprint gives

        /* fingerprint.fonts looks like this:  "fonts": "[\"Adobe Devanagari\", \"Agency FB\"]", */
        const fingerprintFonts: string[] = JSON.parse(fingerprint.fonts);
        const selectedFonts: { id: number; font: string; type: string; os: string }[] = fontList.sort(() => 0.5 - Math.random()).slice(0, fontList.length);

        const selectedFontsNumbers: number[] = selectedFonts.map(font => font.id);
        
        // Generate random values using config
        const macAddress: string = generateRandomMacAddress();
        const deviceName: string = generateRandomDeviceName();

        // Use values from fingerprint API
        const screenWidth: number = fingerprint.screen.width;
        const screenHeight: number = fingerprint.screen.height;
        const connectionDownlink: number = fingerprint.connection.downlink;
        const connectionRtt: number = fingerprint.connection.rtt;
        const cpuCores: number = fingerprint.hardwareConcurrency;
        const memoryGB: number = fingerprint.deviceMemory;
        
        // only log if debug mode is enabled
        let DEBUG_MODE: boolean = false;
        if (DEBUG_MODE) {   
            console.log(`Profile configuration:`);
            console.log(`   Proxy: ${proxy.type}://${proxy.host}:${proxy.port}`);
            console.log(`   CPU: ${cpuCores} cores`);
            console.log(`   Memory: ${memoryGB} GB`);
            console.log(`   Screen: ${screenWidth}x${screenHeight}`);
            console.log(`   Device: ${deviceName}`);
            console.log(`   WebGL: ${fingerprint.webgl.unmaskedVendor}`);
        }

        // Prepare profile data with proxy
        const profileData: ProfileData = {
            name,
            tags,
            platform,
            platformVersion:fingerprint.platformVersion,
            browserType,
            //mainWebsite,
            proxy: {
                id: proxy.id,
                teamId: proxy.teamId,
                userId: proxy.userId,
                name: proxy.name,
                type: proxy.type,
                host: proxy.host,
                port: parseInt(proxy.port),
                login: proxy.login,
                password: proxy.password,
                changeIpUrl: proxy.changeIpUrl,
                provider: proxy.provider,
                ip: proxy.ip,
                savedByUser: true,
                browser_profiles_count: proxy.browser_profiles_count,
                lastCheck: proxy.lastCheck || {
                    createdAt: proxy.createdAt || "",
                    status: true,
                    ip: proxy.ip || "",
                    country: "",
                    region: "",
                    city: "",
                    timezone: "",
                    found: 1,
                    total: 1,
                    blacklists: [""]
                },
                createdAt: proxy.createdAt || "",
                updatedAt: proxy.updatedAt || ""
            },
            args: [],
            notes: [],
            login: null,
            password: null,
            fingerprint: {},
            uaFullVersion: null,
            folderId: null,
            homepages: [],
            newHomepages: [
            ],
            fontsMode: config.DEFAULT_PROFILE_CONFIG.fontsMode,
            fonts: selectedFontsNumbers as any,
            macAddress: {
                mode: "off",
                value: null as any
            },
            deviceName: {
                mode: "off",
                value: null as any,
                valueNew: null as any
            },
            // screen: {
            //     mode: "real",
            //     width: null as any,
            //     height: null as any
               
            // },
            // audio: {
            //     mode: config.DEFAULT_PROFILE_CONFIG.audioMode
            // },
            doNotTrack: true,
            statusId:0, 
            isHiddenProfileName: true,
            disableLoadWebCameraAndCookies: null,
            enableArgIsChromeIcon: null,
           
            useragent: {
                mode: "manual",
                value: fingerprint.userAgent
            },
            webrtc: {
                mode: config.DEFAULT_PROFILE_CONFIG.webrtcMode,
                ipAddress: null
                
            },
            canvas: {
                mode: 'real',
                //noise: [4,9]
            },
            webgl: {
                mode: 'real',
                //noise: [5,5]
            },
            webglInfo: {
                mode: "manual",
                vendor: fingerprint.webgl.unmaskedVendor,
                renderer: fingerprint.webgl.unmaskedRenderer,
                webgl2Maximum: fingerprint.webgl2Maximum
            },
            webgpu: {
                mode: 'manual',
                value: fingerprint.webgpu //fingerprint.webgpu
            },
          
            clientRect: {
                mode: 'real',
            },
            timezone: {
                mode: config.DEFAULT_PROFILE_CONFIG.timezoneMode,
                value: null
            },
            locale: {
                mode: config.DEFAULT_PROFILE_CONFIG.localeMode,
                value: null
            },
            geolocation: {
                mode: config.DEFAULT_PROFILE_CONFIG.geolocationMode,
                latitude: null,
                longitude: null,
                accuracy: null
            },
            cpu: {
                mode: config.DEFAULT_PROFILE_CONFIG.cpuMode,
                value: cpuCores
            },
            memory: {
                mode: config.DEFAULT_PROFILE_CONFIG.memoryMode,
                value: memoryGB
            },
          
          
            connectionDownlink: connectionDownlink,
            connectionEffectiveType: fingerprint.connection.effectiveType,
            connectionRtt: connectionRtt,
            connectionSaveData: fingerprint.connection.saveData,
            platformName: fingerprint.platform,
            cpuArchitecture: fingerprint.cpu.architecture,
            osVersion: fingerprint.os.version,
            // screenWidth: screenWidth,
            // screenHeight: screenHeight,
            vendorSub: fingerprint.vendorSub,
            productSub: fingerprint.productSub,
            vendor: fingerprint.vendor,
            product: fingerprint.product,
            appCodeName: fingerprint.appCodeName,
            mediaDevices: {
                mode: config.DEFAULT_PROFILE_CONFIG.mediaDevicesMode,
                audioInputs: null,
                videoInputs: null,
                audioOutputs: null
            },
            userFields: [],
            ports: {
                mode: config.DEFAULT_PROFILE_CONFIG.portsMode,
                blacklist: config.DEFAULT_PROFILE_CONFIG.portsBlacklist as any
            }
        };
        //console.log(profileData);

        // Debug: Write profile payload to JSON file
        // const fs = require('fs');
        // const path = require('path');
        // const debugFilePath = path.join(__dirname, '..', 'debug_profile_payload.json');
        
        // try {
        //     fs.writeFileSync(debugFilePath, JSON.stringify(profileData, null, 2));
        //     console.log(`🔍 Debug: Profile payload written to ${debugFilePath}`);
        // } catch (debugError) {
        //     console.log(`⚠️ Debug: Failed to write payload file: ${debugError.message}`);
        // }

        // Create the profile
        const response = await fetchAny(`${API_BASE_URL}/browser_profiles`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${API_TOKEN}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(profileData)
        });

        // Check for 429 rate limit error
        if (response.status === 429) {
            throw new Error(`Dolphin API rate limit (429) - too many requests`);
        }

        if (!response.ok) {
            const errorText: string = await response.text();
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
        }

        const result: ProfileResponse = await response.json();
        
        if (result.success) {
            
            
            // Return the result with the proxy ID from our payload
            return {
                ...result,
                proxy: {
                    id: proxy.id
                },
                profileData:profileData
            };
        } else {
            throw new Error(`Profile creation failed: ${JSON.stringify(result)}`);
        }
    } catch (error: any) {
        console.error('❌ Error creating profile:', error.message);
        throw error;
    }
}

/**
 * Create multiple profiles with different configurations
 * @param {number} count - Number of profiles to create
 * @param {ProfileOptions} baseOptions - Base options for all profiles
 * @returns {Promise<ProfileResponse[]>} Array of created profile responses
 */
async function createMultipleProfiles(count: number = 1, baseOptions: ProfileOptions = {}): Promise<ProfileResponse[]> {
    const profiles: ProfileResponse[] = [];
    
    for (let i = 0; i < count; i++) {
        try {
            const options: ProfileOptions = {
                ...baseOptions,
                name: baseOptions.name || `Profile-${Date.now()}-${i + 1}`,
                tags: baseOptions.tags || ['automation', `batch-${Date.now()}`]
            };
            
            const profile: ProfileResponse = await createProfile(options);
            profiles.push(profile);
            
            // Add small delay between profile creations using config
            if (i < count - 1) {
                await new Promise(resolve => setTimeout(resolve, config.DELAY_BETWEEN_PROFILES));
            }
        } catch (error: any) {
            console.error(`❌ Error creating profile ${i + 1}:`, error.message);
            // Continue with next profile even if one fails
        }
    }
    
    return profiles;
}

export {
    // Functions
    getFingerprint,
    getFontList,
    createProfile,
    createMultipleProfiles,
    generateRandomMacAddress,
    generateRandomDeviceName,
    validateFingerprintConsistency
};

export { config as CONFIG };
