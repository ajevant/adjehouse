
interface GeneratedAddress {
    FIRST_NAME: string;
    LAST_NAME?: string;
    [key: string]: any;
}

interface CurrentUser {
    EMAIL: string;
    ADDRESS_COUNTRY: string;
    CARD_NUM?: string;
    CARD_CVV?: string;
    EXPIRY_MONTH?: string;
    EXPIRY_YEAR?: string;
    FIRST_NAME?: string;
    LAST_NAME?: string;
    [key: string]: any;
}

interface HumanInteractions {
    waitForElementRobust: (selector: string, description: string, page: any, timeout: number, logFunction: Function) => Promise<boolean>;
    robustFill: (selector: string, value: string, description: string, page: any, retries: number, timeout: number, logFunction: Function) => Promise<boolean>;
    robustSelect: (selector: string, value: any, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string) => Promise<boolean>;
    robustClick: (selector: string, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string, throwErrors?: boolean, fastMode?: boolean) => Promise<boolean>;
    smoothScrollToElement: (selector: string) => Promise<void>;
}

// Helper function for random delay
const randomDelay = (min: number, max: number): number => {
    return Math.floor(Math.random() * (max - min + 1)) + min;
};

// Helper function to wait for and find payment iframe
const waitForPaymentIframe = async (page: any, logFunction: Function): Promise<any> => {
    let iframeFound = false;
    let iframeElement = null;
    const maxIframeWait = 60;
    let iframeAttempts = 0;
    
    while (!iframeFound && iframeAttempts < maxIframeWait) {
        iframeAttempts++;
        
        if (iframeAttempts % 10 === 0) {
            logFunction(`Looking for iframe... (${iframeAttempts}/${maxIframeWait} seconds)`);
        }
        
        try {
            const iframes = await page.locator('iframe').all();
            for (const frame of iframes) {
                const src = await frame.getAttribute('src');
                if (src && src.includes('payment-p8.secutix.com')) {
                    iframeFound = true;
                    iframeElement = frame;
                    logFunction('Found payment iframe');
                    break;
                }
            }
        } catch (error) {
            // Continue waiting
        }
        
        if (!iframeFound) {
            await page.waitForTimeout(1000);
        }
    }
    
    if (!iframeFound) {
        throw new Error('Payment iframe not found after 60 seconds');
    }
    
    return iframeElement;
};

// Helper function to refresh iframe by reloading its src
const refreshPaymentIframe = async (page: any, logFunction: Function): Promise<void> => {
    try {
        logFunction('Refreshing payment iframe due to network error...');
        const iframes = await page.locator('iframe').all();
        for (const frame of iframes) {
            const src = await frame.getAttribute('src');
            if (src && src.includes('payment-p8.secutix.com')) {
                await frame.evaluate((iframe: any) => {
                    const src = iframe.src;
                    iframe.src = '';
                    iframe.src = src;
                });
                logFunction('Iframe refreshed');
                await page.waitForTimeout(2000);
                break;
            }
        }
    } catch (error) {
        logFunction(`Error refreshing iframe: ${error}`);
    }
};

// Helper function to fill all fields in the form
const fillAllFields = async (
    humanInteractions: HumanInteractions,
    frameLocator: any,
    generatedAddress: GeneratedAddress,
    currentUser: CurrentUser,
    logFunction: Function
): Promise<boolean> => {
    try {
        // Fill card number
        const cardNumberSelectors = [
            'input[id="card_number"]',
            'input[name="CardNumber"]',
        ];
        
        let cardFilled = false;
        for (const selector of cardNumberSelectors) {
            try {
                const fillResult: boolean = await humanInteractions.robustFill(selector, currentUser.CARD_NUM || '4111111111111111', 'Card Number', frameLocator, 2, 60, logFunction);
                if (fillResult) {
                    cardFilled = true;
                    break;
                }
            } catch (error) {
                continue;
            }
        }
        
        if (!cardFilled) {
            throw new Error('Failed to fill card number');
        }
        
        // Fill cardholder name
        const firstName = generatedAddress?.FIRST_NAME || currentUser.FIRST_NAME || 'John';
        const lastName = generatedAddress?.LAST_NAME || currentUser.LAST_NAME || 'Doe';
        const fullName = `${firstName} ${lastName}`;
        
        logFunction(`Using cardholder name: ${fullName}`);
        
        const holderSelectors = [
            'input[id="card_holder"]',
            'input[name="CardHolderName"]',
            'input[name="cardholder"]',
            'input[name="holder_name"]'
        ];
        
        let holderFilled = false;
        for (const selector of holderSelectors) {
            try {
                const fillResult: boolean = await humanInteractions.robustFill(selector, fullName, 'Cardholder Name', frameLocator, 2, 60, logFunction);
                if (fillResult) {
                    holderFilled = true;
                    break;
                }
            } catch (error) {
                continue;
            }
        }
        
        if (!holderFilled) {
            throw new Error('Failed to fill cardholder name');
        }
        
        // Fill expiration month
        const monthSelectors = [
            'select[id="card_expiration_date_month"]',
            'select[name="ExpMonth"]',
        ];
        
        let monthSelected = false;
        for (const selector of monthSelectors) {
            try {
                const monthValue = currentUser.EXPIRY_MONTH ? currentUser.EXPIRY_MONTH.toString().padStart(2, '0') : '06';
                const fillResult: boolean = await humanInteractions.robustSelect(selector, monthValue, 'Expiration Month', frameLocator, 2, 60, logFunction);
                if (fillResult) {
                    monthSelected = true;
                    break;
                }
            } catch (error) {
                continue;
            }
        }
        
        if (!monthSelected) {
            throw new Error('Failed to select expiration month');
        }
        
        // Fill expiration year
        const yearSelectors = [
            'select[id="card_expiration_date_year"]',
            'select[name="ExpYear"]',
        ];
        
        let yearSelected = false;
        for (const selector of yearSelectors) {
            try {
                const yearValue = currentUser.EXPIRY_YEAR ? currentUser.EXPIRY_YEAR.toString() : '2028';
                const fillResult: boolean = await humanInteractions.robustSelect(selector, yearValue, 'Expiration Year', frameLocator, 2, 60, logFunction);
                if (fillResult) {
                    yearSelected = true;
                    break;
                }
            } catch (error) {
                continue;
            }
        }
        
        if (!yearSelected) {
            throw new Error('Failed to select expiration year');
        }
        
        // Fill CVV
        const cvvSelectors = [
            'input[id="card_cvv"]',
            'input[name="VerificationCode"]',
        ];
        
        let cvvFilled = false;
        for (const selector of cvvSelectors) {
            try {
                const fillResult: boolean = await humanInteractions.robustFill(selector, currentUser.CARD_CVV || '123', 'CVV', frameLocator, 2, 60, logFunction);
                if (fillResult) {
                    cvvFilled = true;
                    break;
                }
            } catch (error) {
                continue;
            }
        }
        
        if (!cvvFilled) {
            throw new Error('Failed to fill CVV');
        }
        
        return true;
    } catch (error) {
        return false;
    }
};

const detectVisaOrMastercard = async (
    cardNumber: string
): Promise<string> => {
    if(cardNumber.startsWith('4')){
        return 'Visa';
    }else if(cardNumber.startsWith('5')){
        return 'Mastercard';
    }else{
        return 'Unknown';
    }
}

const MakeCardDefault = async (
    humanInteractions: HumanInteractions,
    page: any,
    logFunction: Function
): Promise<boolean> => {
    const clickCardOption: boolean = await humanInteractions.robustClick('div[aria-controls="stx-lt-manage-card-sidebar-id"]', 'Card option', page, 2, 60, logFunction);
    if(!clickCardOption){
        throw new Error('Failed to click card option');
    }
    const makeDefaultButton: boolean = await humanInteractions.robustClick('button[aria-label="Make default"]', 'Make default button', page, 2, 60, logFunction);
    if(!makeDefaultButton){
        throw new Error('Failed to make card default');
    }
    return true;
}

const checkCardAdded = async (
    page: any,
    humanInteractions: HumanInteractions,
    logFunction: Function
): Promise<boolean> => {
    try{

  
    let cardAdded = false;
        
    for (let i = 0; i < 5; i++) {
        const cardAddedCount = await page?.locator('div[aria-controls="stx-lt-manage-card-sidebar-id"]').count();
        if(cardAddedCount && cardAddedCount > 0){
            cardAdded = true;
            break;
        }
        await page?.waitForTimeout(1000);
    }
    if(!cardAdded){
        return false;
    }


    // Now check if the card is acctually defaulted
    // its defaulted if the svg in '.stx-card-alias-code-container' with class '.remixicon' also HAS THE class '.tw-font-bold'
    let isDefaulted = false;
    let cardContainer = page?.locator('.stx-card-alias-code-container');
    if(cardContainer){
        let svgElement = cardContainer?.locator('.remixicon').first();
        if(svgElement){
            const className = await svgElement.getAttribute('class');
            if(className && className.includes('tw-font-bold')){
                isDefaulted = true;
            }else{
                await MakeCardDefault(humanInteractions, page, logFunction);
                if(!isDefaulted){
                    throw new Error('Failed to make card default');
                }
            }
        }else{
            throw new Error('SVG element not found');
        }
    }else{
        throw new Error('Card container not found');
    }
    return (humanInteractions && isDefaulted);


    }catch(error){
        logFunction(`Error detecting card default: ${error}`);
        return false;
    }

}

const ccFill = async (
    humanInteractions: HumanInteractions, 
    page: any,
    generatedAddress: GeneratedAddress,
    currentUser: CurrentUser, 
    logFunction: Function = console.log
): Promise<boolean | string> => {
    // first we need to select card type, this is not inside iframe yet
    // wait till we find div[id="stx-lottery-payment"]

    const paymentIframeFound: boolean = await humanInteractions.waitForElementRobust('div[id="stx-lottery-payment"]', 'Payment iframe', page, 30, logFunction);
    if(!paymentIframeFound){
        logFunction('Payment frame not found, closing it and readding card')
        const closeButton: boolean = await humanInteractions.robustClick('button[aria-label="Close sidebar"]', 'Close Popup', page, 2, 30, logFunction);
        if(!closeButton){
            throw new Error('Failed to close payment iframe');
        }
        // wait 2 seconds
        await page?.waitForTimeout(2000);
        return 'CLOSED_POPUP';
       
    }


    const cardType: string = await detectVisaOrMastercard(currentUser.CARD_NUM || '4111111111111111');

    if(cardType === 'Unknown'){
        throw new Error('Unknown card type');
    }else if(cardType === 'Visa'){
        const visaSelected: boolean = await humanInteractions.robustClick('label[for="VISA"]', 'Visa option', page, 2, 60, logFunction);
        if(!visaSelected){
            throw new Error('Failed to select visa');
        }
    }else if(cardType === 'Mastercard'){
        const mastercardSelected: boolean = await humanInteractions.robustClick('label[for="MASTERCARD"]', 'Mastercard option', page, 2, 60, logFunction);
        if(!mastercardSelected){
            throw new Error('Failed to select mastercard');
        }
    }



   
    const maxRetries = 2;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            logFunction('Waiting for payment iframe...');
            
            // Wait for iframe
            const iframe = await waitForPaymentIframe(page, logFunction);
            const frameLocator = page.frameLocator('iframe[src*="payment-p8.secutix.com"]');
            
            // Try to fill all fields
            const success = await fillAllFields(humanInteractions, frameLocator, generatedAddress, currentUser, logFunction);
            
            if (success) {
                logFunction('Credit card form filling completed');
                return true;
            } else {
                logFunction(`Failed to fill form (attempt ${attempt}/${maxRetries})`);
                
                if (attempt < maxRetries) {
                    // check if iframe is still there
                    const iframeExists = await page.locator('iframe[src*="payment-p8.secutix.com"]').count();
                    if(iframeExists > 0){
                        await refreshPaymentIframe(page, logFunction);
                    }else{
                        logFunction('Payment iframe not found, closing it and readding card');
                        const closeButton: boolean = await humanInteractions.robustClick('button[aria-label="Close sidebar"]', 'Close Popup', page, 2, 30, logFunction);
                        if(!closeButton){
                            throw new Error('Failed to close payment iframe');
                        }
                        // wait 2 seconds
                        await page?.waitForTimeout(2000);
                        return 'CLOSED_POPUP';
                    }
                }
            }
        } catch (error: any) {
            logFunction(`Error on attempt ${attempt}: ${error.message}`);
            
            if (attempt < maxRetries) {
                await refreshPaymentIframe(page, logFunction);
            } else {
                throw error;
            }
        }
    }
    
    return false;
};

const addCard = async (
    humanInteractions: HumanInteractions, 
    page: any,
    generatedAddress: GeneratedAddress,
    currentUser: CurrentUser, 
    logFunction: Function = console.log
): Promise<boolean> => {
    let maxRetry = 4
    for (let attempt = 1; attempt <= maxRetry; attempt++) {
        try {
            const isCardAdded: boolean = await checkCardAdded(page, humanInteractions, logFunction);
            if(isCardAdded){
                return true;
            }else{
                const addNewCardButton: boolean = await humanInteractions.robustClick('button[aria-label="Add a new card"]', 'Add new card button', page, 2, 60, logFunction);
                if(!addNewCardButton){
                    throw new Error('Failed to click add new card button');
                }
                const ccFillResult: boolean | string = await ccFill(humanInteractions, page, generatedAddress, currentUser, logFunction);
                if(ccFillResult === 'CLOSED_POPUP'){
                    // wait 2 seconds
                    continue;
                }
                if(!ccFillResult){
                    throw new Error('Failed to fill credit card form');
                }else{
                    // now we need to click submit button which is also in the iframe
                    const frameLocator = page.frameLocator('iframe[src*="payment-p8.secutix.com"]');
                    const submitButton: boolean = await humanInteractions.robustClick('.widgetPayNowButton', 'Submit button', frameLocator, 2, 60, logFunction);
                    if(!submitButton){
                        throw new Error('Failed to click submit button');
                    }
                }
                // wait 3 seconds
                await page?.waitForTimeout(3000);
                // dont return true yet, next loop it will check if card is added
                
            }
        } catch (error) {
            continue;
        }   

    }
    return false;
}



export default addCard;