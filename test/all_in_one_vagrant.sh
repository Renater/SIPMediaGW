#!/bin/bash

function select_environment() {
	# Ask the user for deployment option
	echo "Do you want to deploy with Docker? (default: Yes)"
    # Read user input
    read -r choice

	case "$choice" in
		y|Y|yes|YES|"")
			is_docker="true"
			;;
		n|N|no|NO)
			is_docker="false"
			;;
		*)
            echo "Invalid choice. Please try again."
            select_environment
			;;
	esac
}


function select_conferencing_tool() {
    echo "Please select a video conferencing solution:"
    echo "1) Jitsi (default)"
    echo "2) BigBlueButton"
    echo "3) LiveKit"

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
        *)
            echo "Invalid choice. Please try again."
            select_conferencing_tool
            ;;
    esac
}
 
# Run the function to prompt environment
select_environment

# Run the function to prompt user input
select_conferencing_tool

echo "You selected: docker=$is_docker, $browsing"

export BROWSING=${browsing}
export IS_DOCKER=${is_docker}

VAGRANT_VAGRANTFILE=test/Vagrantfile  vagrant up
