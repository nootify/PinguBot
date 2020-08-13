#!/usr/bin/env bash
clear
echo "This script will install the required packages in your current python environment."
echo "A Discord bot token is also required to setup the correct bash environment."
echo "It is highly recommended to make a virtual env (venv) to prevent package conflicts."
printf "\n"
unset choice
while true; do
	read -p "Proceed with setup (y/N)? " choice
	case "$choice" in 
	y|Y)
		clear
		break ;;
	n|N|"")
		printf "\nCancelling pingu setup.\n"
		exit 1 ;;
	*)
		echo "Invalid option. Try again." ;;
	esac
done

printf "Installing required python packages...\n\n"
python -m pip install -r requirements.txt
printf "\n"

unset usr_input
while true; do
	read -s -p "Enter token here (will not be shown in the terminal):"$'\n' usr_input

	if [ "${#usr_input}" -gt 0 ]; then
		echo "PINGU_TOKEN=$usr_input" > .env
		break
	fi
	
	echo "Invalid token. Try again."
done

echo "Pingu setup completed successfully."
echo "To change tokens, simply change PINGU_TOKEN in the .env file."
