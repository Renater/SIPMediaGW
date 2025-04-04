#!/bin/bash

function select_conferencing_tool() {
    echo "Please select a video conferencing solution:"
    echo "1) Jitsi (default)"
    echo "2) BigBlueButton"
    echo "3) LiveKit"
    echo "4) Edumeet"

    # Read user input
    read -r choice

    # Determine the choice
    case $choice in
        1|"") # Default to Jitsi if input is empty
            browsing="jitsi"
            ;;
        2)
            browsing="bigbluebutton"
            ;;
        3)
            browsing="livekit"
            ;;
        4)
            browsing="edumeet"
            ;;
        *)
            echo "Invalid choice. Please try again."
            select_conferencing_tool
            ;;
    esac
}

# Run the function to prompt user input
select_conferencing_tool

echo "You selected: $browsing"

export BROWSING=${browsing}

VAGRANT_VAGRANTFILE=test/Vagrantfile  vagrant up
