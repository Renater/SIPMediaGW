#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

# Load WEBRTC_DOMAINS safely from .env (handles multiline JSON)
if [ -f "$ENV_FILE" ]; then
    WEBRTC_DOMAINS=$(sed -n '/^WEBRTC_DOMAINS=/,/^'\''/p' "$ENV_FILE" \
                     | sed -E '1s/^WEBRTC_DOMAINS=.//; $s/.$//')
else
    echo "File $ENV_FILE not found"
    exit 1
fi

function select_main_application() {
    echo "Please select the gateway role:"
    echo "1) SIP media gateway (default)"
    echo "2) Recording/Transcript media gateway"
    echo "3) Streaming media gateway"

    read -r choice

    case $choice in
        1|"")
            main_app="baresip"
            ;;
        2)
            main_app="recording"
            ;;
        3)
            main_app="streaming"
            ;;
        *)
            echo "Invalid choice. Please try again."
            select_main_application
            ;;
    esac
}

select_main_application
echo "You selected MAIN_APP: $main_app"

# Export variables
export MAIN_APP=${main_app}
export BROWSING=${browsing}

VAGRANT_VAGRANTFILE=test/Vagrantfile vagrant up
