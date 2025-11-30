// Types and interfaces
interface GeneratedAddress {
    FIRST_NAME: string;
    STREET_AND_NUMBER?: string;
    POSTALCODE?: string;
    CITY?: string;
    PHONE_NUMBER?: string;
    [key: string]: any;
}

interface CurrentUser {
    EMAIL: string;
    ADDRESS_COUNTRY: string;
    STREET_AND_NUMBER?: string;
    POSTALCODE?: string;
    CITY?: string;
    PHONE_NUMBER?: string;
    [key: string]: any;
}

interface HumanInteractions {
    waitForElementRobust: (selector: string, description: string, page: any, timeout: number, logFunction: Function) => Promise<boolean>;
    robustFill: (selector: string, value: string, description: string, page: any, retries: number, timeout: number, logFunction: Function) => Promise<boolean>;
    robustSelect: (selector: string, value: any, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string) => Promise<boolean>;
    robustClick: (selector: string, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string, throwErrors?: boolean, fastMode?: boolean) => Promise<boolean>;
    smoothScrollToElement: (selector: string) => Promise<void>;
}

// Helper function to get country code for address form
 const getCountryCodeForAddress = (addressCountry: string): string => {
        const countryMapping = {
            'NED': 'NL',    // Netherlands
            'USA': 'US',    // United States
            'MEX': 'MX',    // Mexico
            'GER': 'DE',    // Germany
            'FRA': 'FR',    // France
            'ESP': 'ES',    // Spain
            'ITA': 'IT',    // Italy
            'BRA': 'BR',    // Brazil
            'ARG': 'AR',    // Argentina
            'ENG': 'GB',    // England -> United Kingdom
            'SCO': 'GB',    // Scotland -> United Kingdom
            'WAL': 'GB',    // Wales -> United Kingdom
            'NIR': 'GB',    // Northern Ireland -> United Kingdom
            'IRL': 'IE',    // Republic of Ireland
            'CAN': 'CA',    // Canada
            'JPN': 'JP',    // Japan
            'KOR': 'KR',    // Korea Republic
            'AUS': 'AU',    // Australia
            'BEL': 'BE',    // Belgium
            'POR': 'PT',    // Portugal
            'SUI': 'CH',    // Switzerland
            'AUT': 'AT',    // Austria
            'DEN': 'DK',    // Denmark
            'SWE': 'SE',    // Sweden
            'NOR': 'NO',    // Norway
            'FIN': 'FI',    // Finland
            'POL': 'PL',    // Poland
            'CZE': 'CZ',    // Czech Republic
            'SVK': 'SK',    // Slovakia
            'HUN': 'HU',    // Hungary
            'CRO': 'HR',    // Croatia
            'SRB': 'RS',    // Serbia
            'UKR': 'UA',    // Ukraine
            'RUS': 'RU',    // Russia
            'TUR': 'TR',    // Turkey
            'GRE': 'GR',    // Greece
            'ISR': 'IL',    // Israel
            'EGY': 'EG',    // Egypt
            'MAR': 'MA',    // Morocco
            'TUN': 'TN',    // Tunisia
            'NGA': 'NG',    // Nigeria
            'GHA': 'GH',    // Ghana
            'CMR': 'CM',    // Cameroon
            'SEN': 'SN',    // Senegal
            'CIV': 'CI',    // Côte d'Ivoire
            'RSA': 'ZA',    // South Africa
            'IRN': 'IR',    // IR Iran
            'KSA': 'SA',    // Saudi Arabia
            'QAT': 'QA',    // Qatar
            'UAE': 'AE',    // United Arab Emirates
            'JOR': 'JO',    // Jordan
            'IRQ': 'IQ',    // Iraq
            'ISL': 'IS',    // Iceland
            'ALB': 'AL',    // Albania
            'MKD': 'MK',    // North Macedonia
            'MNE': 'ME',    // Montenegro
            'BIH': 'BA',    // Bosnia and Herzegovina
            'SVN': 'SI',    // Slovenia
            'EST': 'EE',    // Estonia
            'LVA': 'LV',    // Latvia
            'LTU': 'LT',    // Lithuania
            'BLR': 'BY',    // Belarus
            'MDA': 'MD',    // Moldova
            'ARM': 'AM',    // Armenia
            'AZE': 'AZ',    // Azerbaijan
            'GEO': 'GE',    // Georgia
            'KAZ': 'KZ',    // Kazakhstan
            'UZB': 'UZ',    // Uzbekistan
        };
        
        return countryMapping[addressCountry] || 'NL'; // Default to Netherlands
}

const getUSASateCode = (state: string): string => {
    const stateMapping: any = {
        'Alabama': 'AL',
        'Alaska': 'AK',
        'Arizona': 'AZ',
        'Arkansas': 'AR',
        'California': 'CA',
        'Colorado': 'CO',
        'Connecticut': 'CT',
        'Delaware': 'DE',
        'Florida': 'FL',
        'Georgia': 'GA',
        'Hawaii': 'HI',
        'Idaho': 'ID',
        'Illinois': 'IL',
        'Indiana': 'IN',
        'Iowa': 'IA',
        'Kansas': 'KS',
        'Kentucky': 'KY',
        'Louisiana': 'LA',
        'Maine': 'ME',
        'Maryland': 'MD',
        'Massachusetts': 'MA',
        'Michigan': 'MI',
        'Minnesota': 'MN',
        'Mississippi': 'MS',
        'Missouri': 'MO',
        'Montana': 'MT',
        'Nebraska': 'NE',
        'Nevada': 'NV',
        'New Hampshire': 'NH',
        'New Jersey': 'NJ',
        'New Mexico': 'NM',
        'New York': 'NY',
        'North Carolina': 'NC',
        'North Dakota': 'ND',
        'Ohio': 'OH',
        'Oklahoma': 'OK',
        'Oregon': 'OR',
        'Pennsylvania': 'PA',
        'Rhode Island': 'RI',
        'South Carolina': 'SC',
        'South Dakota': 'SD',
        'Tennessee': 'TN',
        'Texas': 'TX',
        'Utah': 'UT',
        'Vermont': 'VT',
        'Virginia': 'VA',
        'Washington': 'WA',
        'Washington, D.C.': 'DC',   
    }
    // if cant find pick random state from the list
    return stateMapping[state] || Object.values(stateMapping)[Math.floor(Math.random() * Object.values(stateMapping).length)];
}

// Helper function to clean phone number for form
const cleanPhoneNumberForForm = (phoneNumber: string): string => {
    if (!phoneNumber) return '0612345678';
    
    // Remove all non-digit characters
    const cleaned = phoneNumber.replace(/\D/g, '');
    
    // If it starts with country code, remove it
    if (cleaned.startsWith('31') && cleaned.length > 10) {
        return cleaned.substring(2);
    }
    
    // If it's too short, pad with default
    if (cleaned.length < 8) {
        return '0612345678';
    }
    
    return cleaned;
};

const restrictStringLength = (string: string, length: number): string => {
    if(!string) return '';
    return string.substring(0, length);
}

// Helper function for random delay
const randomDelay = (min: number, max: number): number => {
    return Math.floor(Math.random() * (max - min + 1)) + min;
};

const addressFill = async (
    humanInteractions: HumanInteractions, 
    page: any,
    generatedAddress: GeneratedAddress, 
    currentUser: CurrentUser, 
    logFunction: Function = console.log
): Promise<boolean> => {
    try {
        logFunction('Filling address information...');

        // click 18+ checkbox
     
        const clickEighteenPlusCheckboxResult: boolean = await humanInteractions.robustClick('input[id="contactCriteria[AGEVAL]"]', '18+ checkbox', null, 2, 60, logFunction);
        if(clickEighteenPlusCheckboxResult === false){
            throw new Error('Failed to click 18+ checkbox');
        }


        // click tournamant rounds checkboxes
        const checkBoxes =["contactCriteriaROT.values1", "contactCriteriaROT.values3", "contactCriteriaROT.values5", "contactCriteriaROT.values2", "contactCriteriaROT.values4" , "contactCriteriaROT.values6"];
        for(const checkbox of checkBoxes){
            const clickCheckboxResult: boolean = await humanInteractions.robustClick(`input[id="${checkbox}"]`, checkbox, null, 2, 60, logFunction, 'default', false, true);
            if(clickCheckboxResult === false){
                throw new Error(`Failed to click ${checkbox} checkbox`);
            }
        }
        const venues = [
            'ATL', 'BST', 'DAL', 'HOU', 'KC', 'LA', 'MIA', 
            'NY/NJ', 'PHI', 'SF/BA', 'SEA', 'VAN', 'TOR', 
            'GUA', 'MEX', 'MON'
        ];

        const startIndex = Math.floor(Math.random() * (venues.length - 4));
        const selectedVenues = venues.slice(startIndex, startIndex + 5);
        
        const selectElement = page.locator('select[id="contactCriteriaVENUE.values"]');
        await selectElement.scrollIntoViewIfNeeded();
        await page.waitForTimeout(randomDelay(300, 600));
        
        const modifier = process.platform === 'darwin' ? 'Meta' : 'Control';
        await page.keyboard.down(modifier);
        
        for (const venue of selectedVenues) {
            const optionLocator = selectElement.locator(`option[value="${venue}"]`);
            
            // Scroll to the option before clicking to ensure it's in view
            await optionLocator.scrollIntoViewIfNeeded();
            await page.waitForTimeout(randomDelay(100, 200));
            
            const box = await optionLocator.boundingBox();
            
            if (box) {
                const clickX = box.x + box.width * (0.3 + Math.random() * 0.4);
                const clickY = box.y + box.height * (0.3 + Math.random() * 0.4);
                
                await page.mouse.move(clickX, clickY);
                await page.waitForTimeout(randomDelay(50, 150));
                await page.mouse.down();
                await page.waitForTimeout(randomDelay(50, 100));
                await page.mouse.up();
                await page.waitForTimeout(randomDelay(100, 300));
            }
        }
        
        await page.keyboard.up(modifier);

        // fill select fan off
        const fillSelectFanOffResult: boolean = await humanInteractions.robustSelect('select[id="contactCriteriaFanOF26.values0"]', (generatedAddress?.FAN_OF || currentUser.FAN_OF || 'Yes').trim(), 'Fan Of', null, 2, 60, logFunction);
        if(fillSelectFanOffResult === false){
            throw new Error('Failed to fill Fan Of');
        }

        // Fill address1
        const fillAddress1Result: boolean = await humanInteractions.robustFill('input[id="address_line_1"]', restrictStringLength((generatedAddress?.STREET_AND_NUMBER || currentUser.STREET_AND_NUMBER || '123 Main Street').trim(), 37), 'Address Line 1', null, 2, 60, logFunction);
        if(fillAddress1Result === false){
            throw new Error('Failed to fill Address Line 1');
        }
        // fill city
        let cityOptions = ['input[id="address_town"]', 'input[id="address_town_standalone"]']
        for(const cityOption of cityOptions){
            // if it can find the element, use that and fill it
            const element = page.locator(cityOption);
            if(await element.isVisible()){
                const fillCityResult: boolean = await humanInteractions.robustFill(cityOption, (generatedAddress?.CITY || currentUser.CITY || 'Amsterdam').trim(), 'City', null, 2, 60, logFunction);
                if(fillCityResult === false){
                    throw new Error('Failed to fill City');
                }
                break;
            }
        }

        let postCodeOptions = ['input[id="address_zipcode"]', 'input[id="address_zipcode_standalone"]']
        for(const postCodeOption of postCodeOptions){
            const element = page.locator(postCodeOption);
            if(await element.isVisible()){
                const fillPostalCodeResult: boolean = await humanInteractions.robustFill(postCodeOption, (generatedAddress?.POSTALCODE || currentUser.POSTALCODE || '1000 AA').trim(), 'Postal Code', null, 2, 60, logFunction);
                if(fillPostalCodeResult === false){
                    throw new Error('Failed to fill Postal Code');
                }
                break;
            }   
        }
        // scrol down
         await humanInteractions.smoothScrollToElement('select[id="locality_STATE"]');
 
         // if its usa we need to fill state aswell
         if(currentUser?.ADDRESS_COUNTRY === 'USA'){
             const fillStateResult: boolean = await humanInteractions.robustSelect('select[id="locality_STATE"]', getUSASateCode(generatedAddress?.STATE || currentUser.STATE || 'California').trim(), 'State', null, 2, 60, logFunction);
             if(fillStateResult === false){
                 throw new Error('Failed to fill State');
             }
 
         }

        // fill phone
        const fillPhoneResult: boolean = await humanInteractions.robustFill('input[id="mobile_number"]', cleanPhoneNumberForForm(generatedAddress?.PHONE_NUMBER || currentUser.PHONE_NUMBER || '0612345678'), 'Phone Number', null, 2, 60, logFunction);
        if(fillPhoneResult === false){
            throw new Error('Failed to fill Phone Number');
        }

        
        logFunction('Address form filling completed');
        return true;
        
    } catch (error: any) {
        logFunction(`Error filling address form: ${error.message}`);
        // Don't throw error, continue with the process
        return false;
    }
};


export default addressFill;
