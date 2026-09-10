class SlideStreamer {
    constructor(options = {}) {
        this.selector = options.selector;
        this.fps = options.fps || 5;
        this.wsUrl = options.wsUrl || 'ws://localhost:8080/ws';
        this.jpegQuality = options.jpegQuality || 0.7;

        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
        this.ws = null;
        this.intervalId = null;
        this.currentVideo = null;

        this.observer = new MutationObserver(() => this.checkState());
    }

    _injectForceStyle() {
        if (document.getElementById('slide-streamer-force-style')) return;
        const style = document.createElement('style');
        style.id = 'slide-streamer-force-style';
        style.textContent = `
            ${this.selector} {
                width: 1920px !important;
                height: 1080px !important;
                max-width: none !important;
                max-height: none !important;
                min-width: 0 !important;
                min-height: 0 !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                opacity: 0 !important;
                z-index: -1 !important;
            }
        `;
        document.head.appendChild(style);
    }
    start() {
        this._injectForceStyle();
        this.observer.observe(document.body, { childList: true, subtree: true });
        this.checkState();
    }

    stop() {
        this.observer.disconnect();
        this.stopStreaming();
    }

    checkState() {
        const video = document.querySelector(this.selector);
        console.log('[checkState]', !!video);

        if (video && !this.currentVideo) {
            this.currentVideo = video;
            this.startStreaming(video);
        } else if (!video && this.currentVideo) {
            this.stopStreaming();
        }
        // if video !== this.currentVideo but both exist (recycling
        // element), streaming continue — no action needed
    }

    startStreaming(video) {
        this.connectWebSocket();
        this.intervalId = setInterval(() => this.captureAndSend(), 1000 / this.fps);
    }

    stopStreaming() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.currentVideo = null;
    }

    connectWebSocket() {
        this.ws = new WebSocket(this.wsUrl);
        this.ws.binaryType = 'arraybuffer';
    }

    captureAndSend() {
        const video = document.querySelector(this.selector);

        if (!video || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        if (!video.videoWidth || !video.videoHeight) return;

        const MAX_WIDTH = 1280;
        const MAX_HEIGHT = 720;

        const videoWidth = video.videoWidth & ~1;
        const videoHeight = video.videoHeight & ~1;
        console.log(videoWidth, videoHeight);

        const scale = Math.min(
            MAX_WIDTH / videoWidth,
            MAX_HEIGHT / videoHeight,
            1
        );

        const width = Math.floor(videoWidth * scale / 2) * 2;
        const height = Math.floor(videoHeight * scale / 2) * 2;

        this.canvas.width = width;
        this.canvas.height = height;

        this.ctx.drawImage(
            video,
            0, 0,
            videoWidth, videoHeight,
            0, 0,
            width, height
        );

        this.canvas.toBlob(blob => {
            if (!blob) return;
            blob.arrayBuffer().then(buf => {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(buf);
                }
            });
        }, 'image/jpeg', this.jpegQuality);
    }
}

window.SlideStreamer = SlideStreamer;