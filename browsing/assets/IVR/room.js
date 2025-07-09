export class Room {
    constructor(config) {
        this.config = config;
        this.roomId = "";
        this.roomName = "";
        this.roomToken = null;
        this.mappedDomain = null;
        this.meeting = null;
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
            if (authURL) {
                await this.getConferenceToken(authURL, timeout, onError);
            }
            this.displayName = new URLSearchParams(window.location.search).get("displayName");
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
