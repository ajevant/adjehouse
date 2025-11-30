// Types and interfaces
import solveQueueCaptcha from '../../helpers/solveQueueCaptcha';

interface HumanInteractions {
    waitForElementRobust: (selector: string, description: string, page: any, timeout: number, logFunction: Function) => Promise<boolean>;
    robustFill: (selector: string, value: string, description: string, page: any, retries: number, timeout: number, logFunction: Function) => Promise<boolean>;
    robustSelect: (selector: string, value: any, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string) => Promise<boolean>;
    robustClick: (selector: string, description: string, page: any, retries: number, timeout: number, logFunction: Function, mode?: string) => Promise<boolean>;
}


const submitCaptcha = async (
    humanInteractions: HumanInteractions, 
    page: any,
    capsolverKey: string,
    logFunction: Function = console.log,
): Promise<boolean> => {
    try{
        // check if we can find the captcha element img[id="img_captcha"]
        const captchaElement = await humanInteractions.waitForElementRobust('img[id="img_captcha"]', 'captcha image', page, 60, logFunction);
        if(!captchaElement){
            throw new Error('Captcha element not found');
        }
        const captchaSolution = await solveQueueCaptcha(capsolverKey, page, logFunction);
        if(!captchaSolution){
            throw new Error('Failed to solve captcha');
        }


        // now we need to fill the captcha input input[id="secret"]
        const captchaInput = await humanInteractions.robustFill('input[id="secret"]', captchaSolution, 'captcha input', page, 3, 60, logFunction);
        if(!captchaInput){
            throw new Error('Failed to fill captcha input');
        }

        // now we need to click the submit button button[id="submit"]
        const submitButton = await humanInteractions.robustClick('span[id="submit_button"]', 'submit button', page, 3, 60, logFunction);
        if(!submitButton){
            throw new Error('Failed to click submit button');
        }

         return true;
    } catch (error: any) {
        console.error(error.message);
        return false;
    }
}
const logCaptchaPosition = async (
    humanInteractions: HumanInteractions, 
    page: any,
    logFunction: Function = console.log,
): Promise<string> => {
    try{
        // TODO
        return '5 seconds';
    }
    catch(error: any){
        console.error(error.message);
        return 'unknown';
    }
}

const checkQueueResult = async (
    humanInteractions: HumanInteractions, 
    page: any,
    logFunction: Function = console.log,
): Promise<string> => {
    try{
        const stillOnCaptchaPageElements =['span[id="img_captcha"]'];
        const inQueueElements =['div[id="waitdiv"]'];
        const enterQueueElements =['span[id="actionButtonSpan"]'];
      

        for(let i = 0; i < stillOnCaptchaPageElements.length; i++){
            const stillOnCaptchaPageElementVisible: boolean = await page.locator(stillOnCaptchaPageElements[i]).isVisible();
            if(stillOnCaptchaPageElementVisible){
                return 'STILL_ON_CAPTCHA_PAGE';
            }
        }
        for(let i = 0; i < inQueueElements.length; i++){
            const inQueueElementVisible: boolean = await page.locator(inQueueElements[i]).isVisible();
            if(inQueueElementVisible){
                return 'IN_QUEUE';
            }
        }
        for(let i = 0; i < enterQueueElements.length; i++){
            const enterQueueElementVisible: boolean = await page.locator(enterQueueElements[i]).isVisible();
            if(enterQueueElementVisible){
                return 'ON_ENTER_QUEUE_PAGE';
            }
        }
        
        let currentUrl: string = await page.url();
        // if url doenst contain pk and queeu we are passed the queue
        if(!currentUrl.includes('/pkpcontroller/') && !currentUrl.includes('queue')){
            return 'PASSED_QUEUE';
        }
        
        
        return 'UNKNOWN';
    }catch(error: any){
        //console.error(error.message);
        return 'UNKNOWN';
    }
}

const checkAndLogQueuePosition = async (
    humanInteractions: HumanInteractions, 
    page: any,
    logFunction: Function = console.log,
): Promise<boolean | string> => {
    try{
        // Single-shot read: do not wait, just check presence once
        const minLoc = page.locator('span[id="wait_min"]').first();
        const secLoc = page.locator('span[id="wait_sec"]').first();
        const waitTimerLoc = page.locator('#waittimer, [id="waittimer"]').first();

        const [minCount, secCount] = await Promise.all([minLoc.count(), secLoc.count()]);
        if (minCount > 0 && secCount > 0) {
            const [minText, secText] = await Promise.all([
                minLoc.textContent().catch(() => null),
                secLoc.textContent().catch(() => null)
            ]);
            if (minText && secText) {
                const minutes = minText.trim();
                const seconds = secText.trim();
                return `${minutes} minutes and ${seconds} seconds`;
            }
        }

        // If timer numbers are not visible but the timer container exists, report queued state
        const hasWaitTimer = await waitTimerLoc.count();
        if (hasWaitTimer > 0) {
            return 'no timer visible, in queue';
        }

        return false;
    }
    catch(error: any){
        console.error(error.message);
        return false;
    }
}

const queueCompletion = async (
    humanInteractions: HumanInteractions, 
    page: any,
    logFunction: Function = console.log,
    capsolverKey: string,
    errorCount: number = 0,
    startTime: number = Date.now(),
    lastUpdateTime
): Promise<boolean | string> => {
    try{
        let lastQueueUpdate = '' as any;
        let completionResult: string = 'UNKNOWN';
        

        for (let i = 0; i < 7; i++) {
            completionResult = await checkQueueResult(humanInteractions, page, logFunction);
            // Dont instantly return unknown or passed queue cuz it can take a while to load
            if (completionResult !== 'UNKNOWN') break;
            await page.waitForTimeout(5000);
        }   

        if(errorCount > 3){
            return 'PROXY_TIMEOUT';
        }

        switch(completionResult){
            case 'STILL_ON_CAPTCHA_PAGE':
                // retry captcha submission
                logFunction('Retrying captcha submission...', 'warn');
                const submitCaptchaResult = await submitCaptcha(humanInteractions, page, capsolverKey, logFunction);
                if(!submitCaptchaResult){
                    //throw new Error('Failed to submit captcha');
                }
                errorCount++;
                completionResult = 'CONTINUE';
            case 'IN_QUEUE':
                // TODO READ REAL POSITION
                //const captchaPosition = await logCaptchaPosition(humanInteractions, page, logFunction);


                const queuePosition = await checkAndLogQueuePosition(humanInteractions, page, logFunction);
                if(!queuePosition){
                    logFunction('Queue Position not visible', 'warn');
                    lastUpdateTime = Date.now();
                    return 'CONTINUE';
                }else{
                    lastQueueUpdate = queuePosition;
                    logFunction(`Queue position: ${queuePosition}`, 'warn');
                    lastUpdateTime = Date.now();
                }
              

                await page.waitForTimeout(10000);
                completionResult = 'CONTINUE';
                break;
            case 'ON_ENTER_QUEUE_PAGE':
                // click the enter queue button
                logFunction('Enter queue button detect, entering')
                const enterQueueButton = await humanInteractions.robustClick('span[id="actionButtonSpan"]', 'enter queue button', page, 3, 60, logFunction);
                if(!enterQueueButton){
                    throw new Error('Failed to click enter queue button');
                }
                completionResult = 'CONTINUE';
                break;
            case 'PASSED_QUEUE':
                return 'PASSED_QUEUE';
            default:
                completionResult = 'PROXY_TIMEOUT';
        }

        // last queue update has been the same for 3 minutes or more, return proxy timeout
        if(Date.now() - lastUpdateTime > 180000){
            return 'PROXY_TIMEOUT';
        }

        
        if(completionResult === 'CONTINUE'){
            // wait 5 seconds
            await page.waitForTimeout(5000);
            return await queueCompletion(humanInteractions, page, logFunction, capsolverKey, errorCount, startTime, lastUpdateTime);
        }else{
            return completionResult;
        }

    } catch (error: any) {
        console.error(error.message);
        return 'PROXY_TIMEOUT';
    }
}

const sendQueuePassToAPI = async (
    humanInteractions: HumanInteractions, 
    page: any,
    logFunction: Function = console.log,
): Promise<boolean> => {
    try{
       // try to find this cookie AcpAT-v3-10-FWC26-LotteryFCFS
        const cookies = await page.context().cookies();
        const cookie = cookies.find((c: any) => c.name === 'AcpAT-v3-10-FWC26-LotteryFCFS');
        if(!cookie){
            return false;
        }


        // post the cookie to http://152.53.86.201:8000/cookie
        const response = await fetch('http://152.53.86.201:8000/cookie', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                "id": "fifa",
                "cookie": cookie.value
            }),
        });
        if(!response.ok){
            // log response error
            const responseData = await response.json();
            logFunction(`Failed to send cookie to API: ${responseData.error}`, 'error');
            return false;
        }
        logFunction('Cookie sent to API', 'success');
        return true;
    }catch(error: any){
        console.error(error.message);
        return false;
    }
}

const queueHandler = async (
    humanInteractions: HumanInteractions, 
    page: any,
    capsolverKey: string,
    logFunction: Function = console.log,
): Promise<boolean | string> => {
    try{
       
        const submitCaptchaResult = await submitCaptcha(humanInteractions, page, capsolverKey, logFunction);
        if(!submitCaptchaResult){
            throw new Error('Failed to submit captcha');
        }
        // Now its "submitted", but we gotta check if we are in queue
        const queueCompletionResult = await queueCompletion(humanInteractions, page, logFunction, capsolverKey, 0, Date.now(), Date.now());
        if(!queueCompletionResult){
            throw new Error('Failed to complete queue');
        }

        if(queueCompletionResult === 'PASSED_QUEUE'){
            const sendQueuePassToAPIResult = await sendQueuePassToAPI(humanInteractions, page, logFunction);
        }
        
        return queueCompletionResult;
    } catch (error: any) {
        console.error(error.message);
        return 'PROXY_TIMEOUT';
    }
};


export default queueHandler;
