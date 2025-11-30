// Types and interfaces
interface ProfileConfig {
    platform: string;
    platformVersion: string;
    browserType: string;
    browserVersion: string;
    mainWebsite: string;
    fontsMode: string;
    audioMode: string;
    doNotTrack: boolean;
    webrtcMode: string;
    canvasMode: string;
    webglMode: string;
    webgpuMode: string;
    clientRectMode: string;
    timezoneMode: string;
    localeMode: string;
    geolocationMode: string;
    cpuMode: string;
    memoryMode: string;
    screenMode: string;
    mediaDevicesMode: string;
    portsMode: string;
    portsBlacklist: string;
    deletePassword: string;
}

interface RandomRanges {
    audioNoise: { min: number; max: number };
    webglNoise: { min: number; max: number };
    clientRectNoise: { min: number; max: number };
    fontCount: { min: number; max: number };
    latitude: { min: number; max: number };
    longitude: { min: number; max: number };
}

interface Config {
    API_BASE_URL: string;
    LOCAL_API_BASE_URL: string;
    DEFAULT_PROFILE_CONFIG: ProfileConfig;
    MAX_PROFILES_PER_BATCH: number;
    DELAY_BETWEEN_PROFILES: number;
    MAX_RETRIES_FOR_UNUSED_PROXY: number;
    RANDOM_RANGES: RandomRanges;
    VALID_CPU_CORES: number[];
    VALID_MEMORY_GB: number[];
    DEVICE_NAME_PREFIXES: string[];
    DEVICE_NAMES: string[];
    COMMON_TAGS: string[];
}

const config: Config = {
    // API Configuration
    API_BASE_URL: "https://dolphin-anty-api.com",
    LOCAL_API_BASE_URL: "http://localhost:3001/v1.0",
    
    // Default Profile Settings
    DEFAULT_PROFILE_CONFIG: {
        platform: 'macos',
        platformVersion: '15.6.1',
        browserType: 'anty',
        browserVersion: '141',
        mainWebsite: 'google',
        fontsMode: 'manual',
        audioMode: 'real',
        doNotTrack: false,  // Changed to true (On)
        webrtcMode: 'altered',
        canvasMode: 'noise',
        webglMode: 'noise',
        webgpuMode: 'manual',
        clientRectMode: 'real',
        timezoneMode: 'auto',
        localeMode: 'auto',
        geolocationMode: 'auto',
        cpuMode: 'manual',  // Changed to manual for spoofing
        memoryMode: 'manual',  // Changed to manual for spoofing
        screenMode: 'manual',  // CRITICAL: Use fingerprint screen dimensions, not real screen
        mediaDevicesMode: 'real',
        portsMode: 'protect',
        portsBlacklist: '3389,5900,5800,7070,6568,5938,63333,5901,5902,5903,5950,5931,5939,6039,5944,6040,5279,2112',
        deletePassword: 'myStrongPassword' // Default password for profile deletion
    },
    
    // Profile Creation Limits
    MAX_PROFILES_PER_BATCH: 10,
    DELAY_BETWEEN_PROFILES: 1000, // milliseconds
    
    // Proxy Settings
    MAX_RETRIES_FOR_UNUSED_PROXY: 3,
    
    // Random Value Ranges
    RANDOM_RANGES: {
        audioNoise: { min: 1, max: 10 },
        webglNoise: { min: 1, max: 10 },
        clientRectNoise: { min: 1, max: 10 },
        fontCount: { min: 40, max: 120 }, // Updated for macOS realism
        latitude: { min: -90, max: 90 },
        longitude: { min: -180, max: 180 }
    },
    
    // Valid Dolphin Anty CPU and Memory options
    VALID_CPU_CORES: [2, 4, 8, 10, 12, 16, 24, 32],
    VALID_MEMORY_GB: [2, 4, 8, 16, 32, 64, 128],
    
    // Device Name Prefixes (like Dolphin defaults) - Mac only
    DEVICE_NAME_PREFIXES: ['iMac Retina', 'MacBook Pro', 'Mac Pro', 'Mac Mini'],
    
    // Realistic first names for device naming (50+ names)
    DEVICE_NAMES: [
        'Maggie', 'Bella', 'Damian', 'Hallie', 'Braulio', 'Americo', 'Sofia', 'Lucas', 
        'Emma', 'Oliver', 'Ava', 'William', 'Isabella', 'James', 'Sophia', 'Benjamin',
        'Charlotte', 'Mason', 'Amelia', 'Elijah', 'Mia', 'Alexander', 'Harper', 'Michael',
        'Evelyn', 'Ethan', 'Abigail', 'Daniel', 'Emily', 'Matthew', 'Elizabeth', 'Joseph',
        'Mila', 'Sebastian', 'Ella', 'David', 'Madison', 'Carter', 'Scarlett', 'Owen',
        'Victoria', 'Wyatt', 'Aria', 'John', 'Grace', 'Jack', 'Chloe', 'Luke', 'Camila',
        'Julian', 'Penelope', 'Gabriel', 'Layla', 'Grayson', 'Riley', 'Leo', 'Zoey',
        'Jayden', 'Nora', 'Lincoln', 'Lily', 'Isaac', 'Eleanor', 'Anthony', 'Hannah',
        'Hudson', 'Lillian', 'Asher', 'Addison', 'Christopher', 'Aubrey', 'Joshua', 'Ellie',
        'Andrew', 'Stella', 'Nathan', 'Natalie', 'Caleb', 'Zoe', 'Ryan', 'Leah', 'Adrian'
    ],
    
    // Common Tags
    COMMON_TAGS: ['automation', 'fifa', 'gaming', 'test', 'batch']
};

export default config;
