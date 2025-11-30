// Types and interfaces
interface UserData {
    EMAIL: string;
    PASSWORD: string;
    CARD_NUM?: string;
    FAN_OF?: string;
    [key: string]: any;
}

interface DiscordEmbed {
    title: string;
    description: string;
    color: number;
    fields: Array<{
        name: string;
        value: string;
        inline: boolean;
    }>;
    footer: {
        text: string;
        icon_url: string;
    };
    timestamp: string;
}

interface DiscordPayload {
    embeds: DiscordEmbed[];
}

import SettingsHelper from './settingsHelper';

const sendWithRateLimit = async(
    webhookUrl: string,
    payload: DiscordPayload,
    logFunction: Function = console.log,
    maxRetries: number = 4
): Promise<boolean> => {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response: Response = await fetch(webhookUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            // Success
            if (response.ok) {
                return true;
            }
            
            // Rate limited (429)
            if (response.status === 429) {
                const retryAfter = response.headers.get('retry-after');
                const waitTime = retryAfter ? parseInt(retryAfter) * 1000 : Math.pow(2, attempt) * 1000;
                
                if (attempt < maxRetries) {
                    logFunction(`Discord rate limited, retrying in ${waitTime}ms (attempt ${attempt + 1}/${maxRetries})`, 'warn');
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                    continue;
                } else {
                    logFunction(`Discord rate limit exceeded after ${maxRetries} retries`, 'error');
                    return false;
                }
            }
            
            // Other HTTP errors
            if (attempt < maxRetries) {
                const backoffTime = Math.pow(2, attempt) * 1000;
                logFunction(`Discord webhook failed (${response.status}), retrying in ${backoffTime}ms`, 'warn');
                await new Promise(resolve => setTimeout(resolve, backoffTime));
                continue;
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
        } catch (error: any) {
            if (attempt < maxRetries) {
                const backoffTime = Math.pow(2, attempt) * 1000;
                logFunction(`Discord webhook error: ${error.message}, retrying in ${backoffTime}ms`, 'warn');
                await new Promise(resolve => setTimeout(resolve, backoffTime));
            } else {
                throw error;
            }
        }
    }
    
    return false;
};

const sendDiscordWebhook = async(
    user: UserData, 
    success: boolean, 
    logFunction: Function = console.log
): Promise<void> => {
    try {
        const settings = SettingsHelper.getInstance();
        const webhookUrl: string = settings.get('DISCORD_WEBHOOK') as string;
        const last4: string = user.CARD_NUM ? user.CARD_NUM.slice(-4) : 'N/A';
            
        // Get actual selected venues from class property or default
        let selectedVenues: string = 'All venues except Monterrey (15/16 venues selected)';
        
        let embed: DiscordEmbed;
        
        if (success) {
            embed = {
                title: ':white_check_mark: FIFA World Cup Entry Completed!',
                description: 'Successfully entered the FIFA World Cup 26™ Presale Draw for Visa® Cardholders',
                color: 0x5d0fca, // red color for success
                fields: [
                    {
                        name: ':envelope: Email',
                        value: user.EMAIL || 'N/A',
                        inline: true
                    },
                    {
                        name: ':key: Password',
                        value: user.PASSWORD || 'N/A',
                        inline: true
                    },
                    {
                        name: ':credit_card: Card (Last 4)',
                        value: `****${last4}`,
                        inline: true
                    },
                    {
                        name: ':tada: Fan of',
                        value: user.FAN_OF || 'N/A',
                        inline: false
                    },
                ],
                footer: {
                    text: 'FIFA - 魔獸中文軟體',
                    icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
                },
                timestamp: new Date().toISOString()
            };
        } else {
            embed = {
                title: ':x: FIFA World Cup Entry Failed',
                description: 'Failed to enter the FIFA World Cup 26™ Presale Draw for Visa® Cardholders',
                color: 0xff0000, // red color for failure
                fields: [
                    {
                        name: ':envelope: Email',
                        value: user.EMAIL || 'N/A',
                        inline: true
                    },
                    {
                        name: ':key: Password',
                        value: user.PASSWORD || 'N/A',
                        inline: true
                    },
                    {
                        name: ':credit_card: Card (Last 4)',
                        value: `****${last4}`,
                        inline: true
                    },
                    {
                        name: ':tada: Fan of',
                        value: user.FAN_OF || 'N/A',
                        inline: false
                    },
                ],
                footer: {
                    text: 'FIFA - 魔獸中文軟體',
                    icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
                },
                timestamp: new Date().toISOString()
            };
        }
        
        const payload: DiscordPayload = {
            embeds: [embed]
        };
        
        await sendWithRateLimit(webhookUrl, payload, logFunction);
        logFunction('Discord webhook sent successfully');
    } catch (error: any) {
        logFunction(`Error sending Discord webhook: ${error.message}`, 'error');
    }
};

const sendAccountCreationNotification = async(
    user: UserData, 
    logFunction: Function = console.log
): Promise<void> => {
    try {
        const settings = SettingsHelper.getInstance();
        const webhookUrl: string = settings.get('DISCORD_WEBHOOK') as string;
        
        const embed: DiscordEmbed = {
            title: 'FIFA Account Created',
            description: `Account created successfully for ${user.EMAIL}`,
            color: 0x2E8DD6, // blue color for success #0x2E8DD6
            fields: [],
            footer: {
                text: 'FIFA - 魔獸中文軟體',
                icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
            },
            timestamp: new Date().toISOString()
        };
        
        const payload: DiscordPayload = {
            embeds: [embed]
        };
        
        await sendWithRateLimit(webhookUrl, payload, logFunction);
        //logFunction('Account creation notification sent successfully');
    } catch (error: any) {
        logFunction(`Error sending account creation notification: ${error.message}`, 'error');
    }
}

const sendDrawEntryNotification = async(
    user: UserData, 
    logFunction: Function = console.log
): Promise<void> => {
    try {
        const settings = SettingsHelper.getInstance();
        const webhookUrl: string = settings.get('DISCORD_WEBHOOK') as string;

        const embed: DiscordEmbed = {
            title: 'FIFA Draw Entry Completed :partying_face: ',
            description: `Successfully entered fifa draw for ${user.EMAIL}`,
            color: 0x00ff00, // green color for success #0x00ff00
            fields: [
                {
                    name: 'Password',
                    value: user.PASSWORD || 'N/A',
                    inline: true
                },
                {
                    name: 'Last 4 credit card',
                    value: `****${user.CARD_NUM?.slice(-4) || 'N/A'}`,
                    inline: true
                }
                
            ],
            footer: {
                text: 'FIFA - 魔獸中文軟體',
                icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
            },
            timestamp: new Date().toISOString()
        };
        
        const payload: DiscordPayload = {
            embeds: [embed]
        };
        
        await sendWithRateLimit(webhookUrl, payload, logFunction);
    }
    catch (error: any) {
        logFunction(`Error sending draw entry notification: ${error.message}`, 'error');
    }
}

const sendErrorNotification = async(
    user: UserData, 
    errorMessage: string, 
    logFunction: Function = console.log
): Promise<void> => {
    try {
        const settings = SettingsHelper.getInstance();
        const webhookUrl: string = settings.get('DISCORD_WEBHOOK') as string;
        
        const embed: DiscordEmbed = {
            title: 'FIFA Entry Error',
            description: `${errorMessage}`,
            color: 0xffa500, // orange color for warning
            fields: [
                {
                    name: 'Email',
                    value: user.EMAIL || 'N/A',
                    inline: true
                },
            ],
            footer: {
                text: 'FIFA - 魔獸中文軟體',
                icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
            },
            timestamp: new Date().toISOString()
        };
        
        const payload: DiscordPayload = {
            embeds: [embed]
        };
        
        await sendWithRateLimit(webhookUrl, payload, logFunction);
        logFunction('Error notification sent successfully');
    } catch (error: any) {
        logFunction(`Error sending error notification: ${error.message}`, 'error');
    }
};

async function sendFinishedWebhook(
    filename: string,
): Promise<void> {
    try {
        const settings = SettingsHelper.getInstance();
        const webhookUrl: string = settings.get('DISCORD_WEBHOOK') as string;

        const embed: DiscordEmbed = {
            title: 'Cluster Finished processing',
            description: 'File: ' + filename,
            color: 0x800080, // Purple color for cluster finished #0x800080
            fields: [],
            footer: {
                text: 'FIFA - 魔獸中文軟體',
                icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
            },
            timestamp: new Date().toISOString()
        };
        
        const payload: DiscordPayload = {
            embeds: [embed]
        };
        
        await sendWithRateLimit(webhookUrl, payload, console.log);
    }
    catch (error: any) {
        console.error(`Error sending finished webhook: ${error.message}`);
    }
}

async function sendQueuePassExpiredWebhook(
    taskNumber: number,
    userEmail: string
): Promise<void> {
    try {
        const settings = SettingsHelper.getInstance();
        const webhookUrl: string = settings.get('DISCORD_WEBHOOK') as string;

        const embed: DiscordEmbed = {
            title: 'Queue Pass Expired',
            description: `Queue pass cookie has expired and is no longer valid`,
            color: 0xFF0000, // Red color for expired
            fields: [
                {
                    name: 'Issue',
                    value: 'Queue pass cookie did not redirect to auth.fifa.com',
                    inline: false
                }
            ],
            footer: {
                text: 'wallahi astro goat - 魔獸中文軟體',
                icon_url: 'https://cdn.discordapp.com/attachments/1355985146850971876/1430219353474728086/red-chinese-demon-mask-with-letters-and-horns-designed-by-vexels-transparent.png?ex=68f8fb12&is=68f7a992&hm=f0579c25e8a4aee3ff835a32fb49cbf848081935be8bfe23843dc69b960419a0&'
            },
            timestamp: new Date().toISOString()
        };
        
        const payload: DiscordPayload = {
            embeds: [embed]
        };
        
        await sendWithRateLimit(webhookUrl, payload, console.log);
    }
    catch (error: any) {
        console.error(`Error sending queue pass expired webhook: ${error.message}`);
    }
}

export { sendDiscordWebhook, sendErrorNotification, sendAccountCreationNotification, sendDrawEntryNotification, sendFinishedWebhook, sendQueuePassExpiredWebhook };
export default { sendDiscordWebhook, sendErrorNotification, sendAccountCreationNotification, sendDrawEntryNotification, sendFinishedWebhook, sendQueuePassExpiredWebhook };
