export class Room {
    constructor(config) {
        this.config = config;
        this.roomId = "";
        this.roomName = "";
        this.roomToken = null;
        this.mappedDomain = null;
        this.meeting = null;
        this.mailOwner = null;
        this.overlayTimeouts = {};
    }

    fetchWithTimeout(resource, options = {}, timeout = 5000, onError = null) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            controller.abort();
            if (onError) onError('timeout');
        }, timeout);

        options = { ...options, signal: controller.signal };

        return fetch(resource, options)
            .then(response => {
                clearTimeout(timeoutId);
                return response;
            })
            .catch(err => {
                if (onError) onError(err);
                throw err;
            });
    }

    generateRandomString(length = 5) {
        const characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
        let result = '';
        for (let i = 0; i < length; i++) {
            const randomIndex = Math.floor(Math.random() * characters.length);
            result += characters.charAt(randomIndex);
        }
        return result;
    }

    async initRoom(roomId, onSuccess = () => {}, onError = () => {}) {
        this.roomId = roomId;
        this.roomName = roomId;
        this.roomToken = this.config['auth_token']['jwt'];

        const confMapper = this.config['conf_mapper'] || {};
        const mapperURL = confMapper.url;
        const timeout = 5000;
        const authURL = this.config['auth_token']['url'];
        try {
            if (mapperURL) {
                await this.getConferenceName(mapperURL, timeout, onError);
            }
            if(!this.mailOwner) {
                this.roomToken = '';
            }
            if (authURL) {
                await this.getConferenceToken(authURL, timeout, onError);
            }
            let name = new URLSearchParams(window.location.search).get("displayName");
            const ipRegex = /^(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])(\.(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])){3}$/;
            if (ipRegex.test(name)){
                name = "Meeting Room "+ this.generateRandomString(6);
            }
            this.displayName = name;
            onSuccess();
        } catch (err) {
            console.error("Error during Meeting room setup:", err);
            onError(err);
        }
    }

    getConferenceName(mapperURL, timeout, onError) {
        return new Promise(resolve => {
            const url = `${mapperURL}=${this.roomId}`;
            this.fetchWithTimeout(url, { method: 'GET' }, timeout, onError)
                .then(res => res.json())
                .then(data => {
                    if (data.conference) {
                        this.roomName = data['url'] || data['conference'].split('@')[0];
                        this.mappedDomain = data['meeting_instance'] || data['conference'].split('@conference.')[1];
                        if("mail_owner" in data) {
                            this.mailOwner = data['mail_owner'];
                        }
                        resolve();
                    } else {
                        onError(data);
                    }
                })
                .catch(onError);
        });
    }

    getConferenceToken(authURL, timeout, onError) {
        return new Promise(resolve => {
            const regex = new RegExp(this.config['auth_token']['secure_room_regexp'] || '.*');
            if (!regex.test(this.roomName)) {
                resolve();
                return;
            }

            const url = `${authURL}?jwt=true&roomName=${this.roomName}&domain=${this.mappedDomain}`;
            this.fetchWithTimeout(url, { method: 'GET' }, timeout, onError)
                .then(res => res.json())
                .then(data => {
                    if (data.jwt) {
                        this.roomToken = data.jwt;
                    }
                    resolve();
                })
                .catch(() => resolve()); // Silent fail
        });
    }
}
