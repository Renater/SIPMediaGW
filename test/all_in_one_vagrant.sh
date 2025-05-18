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

function select_main_application() {
    echo "Please select the gateway role:"
    echo "1) SIP media gateway (default)"
    echo "2) Recording/Transcript media gateway"
    echo "3) Streaming media gateway"

    # Read user input
    read -r choice

    # Determine the choice
    case $choice in
        1|"") # Default to Jitsi if input is empty
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

# Prompt user input
select_conferencing_tool
echo "You selected: $browsing"
select_main_application
echo "You selected: $main_app"


export BROWSING=${browsing}
export MAIN_APP=${main_app}

VAGRANT_VAGRANTFILE=test/Vagrantfile  vagrant up

