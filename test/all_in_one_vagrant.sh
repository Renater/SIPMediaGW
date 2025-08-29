#!/bin/bash

ENV_FILE="../.env"

# Load WEBRTC_DOMAINS safely from .env (handles multiline JSON)
if [ -f "$ENV_FILE" ]; then
    WEBRTC_DOMAINS=$(sed -n '/^WEBRTC_DOMAINS=/,/^'\''/p' "$ENV_FILE" \
                     | sed -E '1s/^WEBRTC_DOMAINS=.//; $s/.$//' )
    # Clean and normalize JSON to avoid parse errors
    WEBRTC_DOMAINS=$(echo "$WEBRTC_DOMAINS" | jq -c .)
else
    echo "File $ENV_FILE not found"
    exit 1
fi


#echo "$WEBRTC_DOMAINS" | jq .

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

function select_conferencing_tool() {
    echo "Do you want to pre-select a WebRTC conferencing tool?"
    echo "0) No"

    # Extract keys and names together with jq (tab-separated)
    mapfile -t entries < <(echo "$WEBRTC_DOMAINS" | jq -r 'to_entries[] | "\(.key)\t\(.value.name)"')

    i=1
    declare -gA mapping
    for entry in "${entries[@]}"; do
        key=$(echo "$entry" | cut -f1)
        name=$(echo "$entry" | cut -f2-)
        echo "$i) $name"
        mapping[$i]=$key
        ((i++))
    done

    read -r choice

    if [ "$choice" == "0" ] || [ -z "$choice" ]; then
        browsing=""
    elif [[ -n "${mapping[$choice]}" ]]; then
        browsing="${mapping[$choice]}"
    else
        echo "Invalid choice. Please try again."
        select_conferencing_tool
    fi
}



# Step 1: main application role
select_main_application
echo "You selected MAIN_APP: $main_app"

# Step 2: conferencing tool (optional)
select_conferencing_tool
if [ -n "$browsing" ]; then
    echo "You selected BROWSING: $browsing"
else
    echo "No WebRTC tool selected"
fi

# Export variables
export MAIN_APP=${main_app}
export BROWSING=${browsing}

VAGRANT_VAGRANTFILE=test/Vagrantfile vagrant up

