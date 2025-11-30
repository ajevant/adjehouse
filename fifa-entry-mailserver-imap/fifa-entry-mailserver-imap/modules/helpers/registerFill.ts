// Types and interfaces
interface GeneratedAddress {
    FIRST_NAME: string;
    [key: string]: any;
}

interface CurrentUser {
    EMAIL: string;
    ADDRESS_COUNTRY: string;
    [key: string]: any;
}

interface HumanInteractions {
    waitForElementRobust: (selector: string, description: string, page: any, timeout: number, logFunction: Function) => Promise<boolean>;
    robustFill: (selector: string, value: string, description: string, page: any, retries: number, timeout: number, logFunction: Function) => Promise<boolean>;
    robustSelect: (selector: string, value: any, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string) => Promise<boolean>;
    robustClick: (selector: string, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string) => Promise<boolean>;
}

const registerFill = async (
    humanInteractions: HumanInteractions, 
    generatedAddress: GeneratedAddress, 
    currentUser: CurrentUser, 
    logFunction: Function = console.log,
    submitLock?: { acquire: () => Promise<() => void> },
    type: 'entry' | 'account' | 'entry-queuepass' = 'entry'

): Promise<boolean> => {
    try{
        const registerFormVisible: boolean = await humanInteractions.waitForElementRobust('form[id="frmRegister"]', 'Register form', null, 60, logFunction);
        if(registerFormVisible === false){
            throw new Error('Register form not loaded');
        }

        // Randomize logical fill order for reduced predictability
        // Strategy:
        // - Variant A (~25%): DOB first (sometimes year-first), then name/email
        // - Variant B (~60%): name/email first, then DOB (default)
        // - Variant C (~15%): name, then DOB with year-first, then email
        const variant = Math.random();

        if (variant < 0.25) {
            // Variant A: DOB first
            const dobOrder = Math.random() < 0.5 ? ['year', 'month', 'day'] : ['day', 'month', 'year'];
            logFunction(`📋 Using fill strategy: Variant A (DOB first: ${dobOrder.join('→')} → name/email)`);
            for (const part of dobOrder) {
                if (part === 'day') {
                    const dayOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="day"]', Math.floor(Math.random() * 28) + 1, 'day of birth', null, 3, 60, logFunction);
                    if (!dayOfBirthResult) throw new Error('Failed to select day of birth');
                } else if (part === 'month') {
                    const monthOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="month"]', Math.floor(Math.random() * 12) + 1, 'month of birth', null, 3, 60, logFunction);
                    if (!monthOfBirthResult) throw new Error('Failed to select month of birth');
                } else {
                    const yearOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="year"]', Math.floor(Math.random() * 16) + 1980, 'year of birth', null, 3, 60, logFunction);
                    if (!yearOfBirthResult) throw new Error('Failed to select year of birth');
                }
                // Small randomized pause between DOB fields
                await new Promise(resolve => setTimeout(resolve, Math.floor(300 + Math.random() * 900)));
            }

            // Then fill name & email
            const fillFirstNameResult: boolean = await humanInteractions.robustFill('input[id="firstname"]', generatedAddress.FIRST_NAME, 'firstname', null, 3, 60, logFunction);
            if (!fillFirstNameResult) throw new Error('Failed to fill first name');

    
            if(type === 'entry'){  
                const lastnameFillResult: boolean = await humanInteractions.robustFill('input[id="lastname"]', generatedAddress.LAST_NAME, 'Last name', null, 3, 60, logFunction);
                if(!lastnameFillResult){
                    throw new Error('Failed to fill last name');
                }

            }
          
            const fillEmailResult: boolean = await humanInteractions.robustFill('input[id="email"]', currentUser.EMAIL, 'email', null, 3, 60, logFunction);
            if (!fillEmailResult) throw new Error('Failed to fill email');

        } else if (variant < 0.85) {
            // Variant B: name/email first (default)
            logFunction(`📋 Using fill strategy: Variant B (name/email first → DOB natural order)`);
            const fillFirstNameResult: boolean = await humanInteractions.robustFill('input[id="firstname"]', generatedAddress.FIRST_NAME, 'firstname', null, 3, 60, logFunction);
            if (!fillFirstNameResult) throw new Error('Failed to fill first name');

            if(type === 'entry'){  
                const lastnameFillResult: boolean = await humanInteractions.robustFill('input[id="lastname"]', generatedAddress.LAST_NAME, 'Last name', null, 3, 60, logFunction);
                if(!lastnameFillResult){
                    throw new Error('Failed to fill last name');
                }

            }
            const fillEmailResult: boolean = await humanInteractions.robustFill('input[id="email"]', currentUser.EMAIL, 'email', null, 3, 60, logFunction);
            if (!fillEmailResult) throw new Error('Failed to fill email');

            // Then DOB in natural order but with small random pauses
            const dayOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="day"]', Math.floor(Math.random() * 28) + 1, 'day of birth', null, 3, 60, logFunction);
            if (!dayOfBirthResult) throw new Error('Failed to select day of birth');
            await new Promise(resolve => setTimeout(resolve, Math.floor(200 + Math.random() * 800)));
            const monthOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="month"]', Math.floor(Math.random() * 12) + 1, 'month of birth', null, 3, 60, logFunction);
            if (!monthOfBirthResult) throw new Error('Failed to select month of birth');
            await new Promise(resolve => setTimeout(resolve, Math.floor(200 + Math.random() * 800)));
            const yearOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="year"]', Math.floor(Math.random() * 16) + 1980, 'year of birth', null, 3, 60, logFunction);
            if (!yearOfBirthResult) throw new Error('Failed to select year of birth');

        } else {
            // Variant C: name, then DOB with year-first, then email
            logFunction(`📋 Using fill strategy: Variant C (name → DOB year-first → email)`);
            const fillFirstNameResult: boolean = await humanInteractions.robustFill('input[id="firstname"]', generatedAddress.FIRST_NAME, 'firstname', null, 3, 60, logFunction);
            if (!fillFirstNameResult) throw new Error('Failed to fill first name');

            if(type === 'entry'){  
                const lastnameFillResult: boolean = await humanInteractions.robustFill('input[id="lastname"]', generatedAddress.LAST_NAME, 'Last name', null, 3, 60, logFunction);
                if(!lastnameFillResult){
                    throw new Error('Failed to fill last name');
                }

            }

            // Year-first DOB
            const yearOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="year"]', Math.floor(Math.random() * 16) + 1980, 'year of birth', null, 3, 60, logFunction);
            if (!yearOfBirthResult) throw new Error('Failed to select year of birth');
            await new Promise(resolve => setTimeout(resolve, Math.floor(250 + Math.random() * 900)));
            const monthOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="month"]', Math.floor(Math.random() * 12) + 1, 'month of birth', null, 3, 60, logFunction);
            if (!monthOfBirthResult) throw new Error('Failed to select month of birth');
            await new Promise(resolve => setTimeout(resolve, Math.floor(200 + Math.random() * 700)));
            const dayOfBirthResult: boolean = await humanInteractions.robustSelect('select[id="day"]', Math.floor(Math.random() * 28) + 1, 'day of birth', null, 3, 60, logFunction);
            if (!dayOfBirthResult) throw new Error('Failed to select day of birth');

            // Finally email
            const fillEmailResult: boolean = await humanInteractions.robustFill('input[id="email"]', currentUser.EMAIL, 'email', null, 3, 60, logFunction);
            if (!fillEmailResult) throw new Error('Failed to fill email');
        }

        // Gender
        const genderResult: boolean = await humanInteractions.robustSelect('select[id="gender"]', "male", 'gender', null, 3, 60, logFunction); 
        if(!genderResult){
            throw new Error('Failed to select gender');
        }
        const countrySelectResult: boolean = await humanInteractions.robustSelect('select[id="country"]', currentUser.ADDRESS_COUNTRY, 'country', null, 3, 60, logFunction); 
        if(!countrySelectResult){
            throw new Error('Failed to select language');
        }

        const languageSelectResult: boolean = await humanInteractions.robustSelect('select[id="preferredLanguage"]', 'English', 'language', null, 3, 60, logFunction, 'exitDropdown'); 
        if(!languageSelectResult){
            throw new Error('Failed to select language');
        }

    
    // Small pause with greater variance before acquiring submit lock
    await new Promise(resolve => setTimeout(resolve, Math.floor(1500 + Math.random() * 4500)));
        
        // ACQUIRE LOCK BEFORE SUBMITTING FIRST REGISTRATION FORM
        let releaseLock: (() => void) | undefined;
        if (submitLock) {
            logFunction('Waiting for submit lock (initial registration)...');
            releaseLock = await submitLock.acquire();
            logFunction('Submit lock acquired for initial registration');
        }
        
        let submitError: any = undefined;
        try {
            const clickRegisterButtonResult: boolean = await humanInteractions.robustClick('button[id="btnSubmitRegister"]', 'Register button', null, 3, 60, logFunction); 
            if(!clickRegisterButtonResult){
                throw new Error('Failed to click register button');
            }
        } catch (err) {
            submitError = err;
            logFunction(`Error during initial registration submit: ${err}`);
        } finally {
            // CRITICAL: Wait ~1.5-4s before releasing lock to reduce predictability
            if (releaseLock) {
                try {
                    logFunction('Waiting ~1.5-4 seconds before releasing initial registration lock...');
                    await new Promise(resolve => setTimeout(resolve, Math.floor(1500 + Math.random() * 2500)));
                } catch (waitError: any) {
                    logFunction(`Error during lock wait: ${waitError}`);
                }

                logFunction('🔒 Releasing submit lock for initial registration');
                releaseLock();
            }
            
            // Re-throw error after lock is released
            if (submitError) {
                throw submitError;
            }
        }
        
        return true;
    } catch (error: any) {
        throw error;
    }
};


export default registerFill;
