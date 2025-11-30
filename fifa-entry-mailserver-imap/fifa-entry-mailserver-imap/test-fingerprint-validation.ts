/**
 * Test script to demonstrate fingerprint validation
 * This shows how the new validation function catches inconsistent fingerprints
 */

import { getFingerprint, validateFingerprintConsistency } from './helpers/profileCreator';

async function testFingerprintValidation() {
    console.log('🔍 Testing Fingerprint Validation System\n');
    console.log('=' .repeat(60));
    
    try {
        // This will automatically retry until a valid fingerprint is found
        console.log('\n📡 Fetching validated fingerprint from API...\n');
        const fingerprint = await getFingerprint('macos', 'anty', '141');
        
        console.log('✅ Successfully obtained valid fingerprint!\n');
        console.log('📊 Fingerprint Details:');
        console.log(`   CPU Architecture: ${fingerprint.cpu.architecture}`);
        console.log(`   Hardware Concurrency: ${fingerprint.hardwareConcurrency} cores`);
        console.log(`   Platform Version: ${fingerprint.platformVersion}`);
        console.log(`   WebGL Vendor: ${fingerprint.webgl.unmaskedVendor}`);
        console.log(`   WebGL Renderer: ${fingerprint.webgl.unmaskedRenderer}`);
        
        // Parse WebGPU to show it matches
        try {
            const webgpuData = JSON.parse(fingerprint.webgpu);
            console.log(`   WebGPU Vendor: ${webgpuData.info.vendor}`);
            console.log(`   WebGPU Architecture: ${webgpuData.info.architecture}`);
        } catch (e) {
            console.log('   WebGPU: Unable to parse');
        }
        
        console.log('\n' + '=' .repeat(60));
        
        // Demonstrate the validation function
        const validation = validateFingerprintConsistency(fingerprint);
        console.log(`\n🔬 Validation Result: ${validation.isValid ? '✅ PASS' : '❌ FAIL'}`);
        if (!validation.isValid) {
            console.log('Reasons:');
            validation.reasons.forEach(reason => console.log(`   - ${reason}`));
        }
        
    } catch (error: any) {
        console.error('\n❌ Error:', error.message);
    }
}

// Run the test
testFingerprintValidation();

