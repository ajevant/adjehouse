import https from 'https';

/**
 * Helper function to make HTTPS POST requests
 */
function httpsPost(url: string, data: any): Promise<any> {
    return new Promise((resolve, reject) => {
        const postData = JSON.stringify(data);
        const urlObj = new URL(url);
        
        const req = https.request({
            hostname: urlObj.hostname,
            port: 443,
            path: urlObj.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            }
        }, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                try {
                    resolve(JSON.parse(body));
                } catch (e) {
                    reject(new Error(`Failed to parse: ${body}`));
                }
            });
        });
        
        req.on('error', reject);
        req.write(postData);
        req.end();
    });
}

/**
 * Solve FIFA queue captcha using CapSolver
 * @param capsolverKey - The CapSolver API key
 * @param page - Playwright page object
 * @param log - Logging function
 * @returns The solved captcha code or null if failed
 */
 async function solveQueueCaptcha(
    capsolverKey: string, 
    page: any, 
    log: Function = console.log
): Promise<string | null> {
    try {
        log('Taking screenshot of captcha...');
        let screenshotBuffer: Buffer | null = null;
        let screenshotAttempts = 0;
        const maxScreenshotAttempts = 3;
        
        while (!screenshotBuffer && screenshotAttempts < maxScreenshotAttempts) {
            screenshotAttempts++;
            try {
                const captchaImage = await page.locator('#img_captcha');
                if (captchaImage) {
                    screenshotBuffer = await captchaImage.screenshot() as Buffer;
                    if (screenshotBuffer && screenshotBuffer.length > 0) {
                        log(`Screenshot captured (${screenshotBuffer.length} bytes)`);
                        break;
                    }
                }
            } catch (error: any) {
                log(`Screenshot attempt ${screenshotAttempts} failed: ${error.message}`, 'warn');
            }
            
            if (screenshotAttempts < maxScreenshotAttempts) {
                log(`Waiting 2s before screenshot retry...`);
                await page.waitForTimeout(2000);
            }
        }
        
        if (!screenshotBuffer || screenshotBuffer.length === 0) {
            log('Failed to capture captcha screenshot after 3 attempts', 'error');
            log('Refreshing page to try again...');
            await page.reload();
            await page.waitForTimeout(2000);
            return null;
        }
        
        const base64 = screenshotBuffer.toString('base64');
        
        log('Solving captcha with CapSolver...');
        
        // Create task with CapSolver
        const createTaskResponse = await httpsPost('https://api.capsolver.com/createTask', {
            clientKey: capsolverKey,
            task: {
                type: 'ImageToTextTask',
                module: 'module_016',
                body: base64
            }
        });
        
        if (createTaskResponse.errorId !== 0) {
            log(`CapSolver createTask error: ${createTaskResponse.errorCode}`);
            return null;
        }
        
        log(`Task solution: ${createTaskResponse.solution?.text}`);
        return createTaskResponse.solution?.text;
        
        // Poll for solution
        // let solution: string | null = null;
        // const maxAttempts = 30;
        // let attempts = 0;
        
        // while (!solution && attempts < maxAttempts) {
        //     attempts++;
        //     await new Promise(resolve => setTimeout(resolve, 2000));
            
        //     const getResultResponse = await httpsPost('https://api.capsolver.com/getTaskResult', {
        //         clientKey: capsolverKey,
        //         taskId: taskId
        //     });
            
        //     if (getResultResponse.errorId !== 0) {
        //         log(`CapSolver getTaskResult error: ${getResultResponse.errorCode}`);
        //         continue;
        //     }
            
        //     if (getResultResponse.status === 'ready') {
        //         solution = getResultResponse.solution?.text;
        //         if (solution && solution.length === 5) {
        //             log(`Solved: ${solution}`);
        //             return solution;
        //         }
        //     } else if (getResultResponse.status === 'processing') {
        //         log(`Task still processing... (attempt ${attempts}/${maxAttempts})`);
        //     } else {
        //         log(`Task status: ${getResultResponse.status}`);
        //         break;
        //     }
        // }
        
        // log('Failed to get solution from CapSolver after max attempts');
        // return null;
    } catch (error: any) {
        log(`Error solving captcha: ${error.message}`, 'error');
        return null;
    }
}


export default solveQueueCaptcha;
