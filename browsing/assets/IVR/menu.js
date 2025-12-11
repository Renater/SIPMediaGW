class Menu {
    constructor() {
        this.meeting = window.meeting;
        this.overlayTimeouts = {};
        this.img = { "icon": null,
                     "dtmf": null};
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

    createOverlayImage(imgKey, bt, left, timeout = 0) {
        var imId = "menu_"+imgKey;
        let existing = document.getElementById(imId);
        if (!existing) {
          const img = document.createElement('img');
          img.id = imId;
          img.src = this.img[imgKey];
          img.style.position = "fixed";
          img.style.bottom = bt;
          img.style.left = left;
          img.style.zIndex = "9999";
          let wrapper = document.getElementById("wrapper")
          if (!wrapper) {
              wrapper = document.createElement("div");
              wrapper.id = "wrapper";
          }
          wrapper.appendChild(img);
        } else {
          existing.style.display = "block";
        }
        if (timeout > 0) {
          setTimeout(() => this.hideOverlayImage(imId), timeout);
        }
    }

    showOverlayImage(id) {
        const img = document.getElementById(id);
        if (img) {
          img.style.display = "block";
        }
    }

    hideOverlayImage(id) {
        const img = document.getElementById(id);
        if (img) {
          img.style.display = "none";
        }
    }

    toggleOverlayImage(id, timeout = 5000) {
        const img = document.getElementById(id);
      
        if (img && img.style.display=="block") {
          this.hideOverlayImage(id);
          clearTimeout(this.overlayTimeouts[id]);
        } else {
          this.showOverlayImage(id, 0);
          if (this.overlayTimeouts[id]) {
            clearTimeout(this.overlayTimeouts[id]);
          }
          this.overlayTimeouts[id] = setTimeout(() => {
            this.hideOverlayImage(id);
            delete this.overlayTimeouts[id];
          }, timeout);
        }
    }

    interact(key){
        if(key == "#"){
            this.toggleOverlayImage('menu_dtmf', 5000);
        } 
        else if(key == "*"){
            this.toggleOverlayImage('menu_icon', 5000);
        }
        else {
            this.meeting.interact(key);
        }
    }

    async show() {
        this.createOverlayImage('icon', '20px', '20px', 30000)
        this.createOverlayImage('dtmf', '10px', '10px', 5000)
        try {
            document.addEventListener('keydown', (e) => {
                const key = e.key;
                if ((key >= '0' && key <= '9') ||
                     key === '#' || key === 's' || key === '*') {
                    e.preventDefault();
                    this.interact(key);
                }
            }, {capture: true});
        } catch (err) {
            console.error("Error during Menu setup:", err);
            onError(err);
        }
    }
}

window.Menu = Menu;