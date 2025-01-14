#!/bin/bash

# Initialize the flags
yes_flag=false
help_flag=false


echo "Wormstation-client installation script"
echo "--------------------------------------"
echo
echo "Make sure you are running this script as a user (not root)."
echo "This script will install the following dependencies:"
echo "    - git"
echo "    - python3"
echo "    - smbclient"
echo "    - opencv-python"
echo "    - picam (symbolic link to cam.py)"
echo "    - /etc/.smbpicreds (credential file for smbclient)"
echo "    - Add current user to 'gpio', 'video' and 'input' groups"
echo "    - Modify /etc/dphys-swapfile to extend swap size to 2GB"
echo "    - Add specific sudo privileges for the current user"
echo "    - Create a udev rule for FT232H"
echo

# Process command line arguments
while getopts ":hy" opt; do
    case $opt in
        y)
            yes_flag=true
            ;;
        h)
            help_flag=true
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
    esac
done

# Display help and exit if -h flag is used
if [ "$help_flag" = true ]; then
    echo "Usage: $(basename $0) [-y] [-h]"
    echo "  -y    Automatically install dependencies without confirmation."
    echo "  -h    Display this help message."
    exit 0
fi

# Ask for confirmation if -y flag is not used
if [ "$yes_flag" = false ]; then
    read -p "Do you want to continue? (y/n): " continue_install
    continue_install=${continue_install:-y}
    if [[ "$continue_install" =~ ^[Nn]$ ]]; then
        echo "Installation aborted."
        exit 0
    fi
fi

# Function to install a package using apt
install_package() {
    local package=$1
    if ! command -v $package &> /dev/null; then
        echo "$package is not installed. Installing $package using apt..."
        if [ "$yes_flag" = true ]; then
            sudo apt update
            sudo apt install $package -y
        else
            read -p "Do you want to install $package? (y/n): " install_package
            install_package=${install_package:-y}
            if [[ "$install_package" =~ ^[Yy]$ ]]; then
                sudo apt update
                sudo apt install $package -y
            fi
        fi
    else
        echo "$package installation found."
    fi
}

# Install required packages
install_package git
install_package python3
install_package smbclient

# Get the directory of this script
script_dir=$(dirname "$(realpath "$0")")

# Create a symbolic link for picam
script_path="$script_dir/cam.py"

if sudo ln -sfn $script_path /usr/local/bin/picam; then
    echo "Symbolic link 'picam' successfully created or updated in /usr/local/bin."
    echo "New link: $(readlink -f /usr/local/bin/picam)"
else
    echo "Failed to create symbolic link. Please check the script path and try again."
fi

# Initialize the list of groups the user is not part of
missing_groups=()

# Check if user is part of gpio group
if ! groups | grep -q '\bgpio\b'; then
    missing_groups+=("gpio")
fi

# Check if user is part of video group
if ! groups | grep -q '\bvideo\b'; then
    missing_groups+=("video")
fi

# Check if user is part of input group
if ! groups | grep -q '\binput\b'; then
    missing_groups+=("input")
fi

# If there are missing groups, prompt the user
if [ ${#missing_groups[@]} -ne 0 ]; then
    echo "You are not part of the following required groups: ${missing_groups[@]}"
    if [ "$yes_flag" = true ]; then
        add_to_groups="y"
    else
        read -p "Do you want to add yourself to these groups? (y/n): " add_to_groups
        add_to_groups=${add_to_groups:-y}
    fi
    if [[ "$add_to_groups" =~ ^[Yy]$ ]]; then
        for group in "${missing_groups[@]}"; do
            sudo usermod -aG $group $USER
        done
        echo "Added user to the required groups. Changes will take effect after logging out and back in."
    else
        echo "You chose not to add yourself to the required groups. Some functionalities may not work properly."
    fi
else
    echo "User is already part of all required groups."
fi

# Disable services with security vulnerabilities
echo "Disabling services with security vulnerabilities..."
sudo systemctl stop cups-browsed.service
sudo systemctl disable cups-browsed.service

# Install Python dependencies from requirements.txt
echo "Installing Python dependencies from requirements.txt..."

if [ -f "$script_dir/requirements.txt" ]; then
    if [ "$yes_flag" = true ]; then
        pip3 install -r "$script_dir/requirements.txt"
    else
        read -p "Do you want to install the Python dependencies from requirements.txt? (y/n): " install_libs
        install_libs=${install_libs:-y}
        if [[ "$install_libs" =~ ^[Yy]$ ]]; then
            pip3 install -r "$script_dir/requirements.txt"
        fi
    fi
else
    echo "ERROR: requirements.txt not found in $script_dir. Python dependencies were not installed."
fi

# Check if /etc/.smbpicreds exists
if [ ! -f /etc/.smbpicreds ]; then
    echo "No credential file for smbclient was found (/etc/.smbpicreds)."
    if [ "$yes_flag" = true ]; then
        smbcred_choice="2"
    else
        read -p "Do you want to:
        1. Locate an existing credential file
        2. Generate /etc/.smbpicreds
        3. Ignore (Videos will be stored locally)
    Enter your choice (1/2/3): " smbcred_choice
        smbcred_choice=${smbcred_choice:-2}
    fi

    case "$smbcred_choice" in
        1)
            read -p "Enter the full path to the existing credential file: " existing_cred_file
            if [ -f "$existing_cred_file" ]; then
                sudo cp "$existing_cred_file" /etc/.smbpicreds
                sudo chmod 600 /etc/.smbpicreds
                sudo chown $USER:$USER /etc/.smbpicreds
                echo "Credential file copied to /etc/.smbpicreds with read and write access for current user."
            else
                echo "File not found."
            fi
            ;;
        2)
            echo
            echo "NOTE: It is recommended to have a dedicated NAS user with limited rights"
            echo "    to be created for that purpose as credentials will be stored as plain text"
            echo
            read -p "Enter NAS username: " smb_username
            read -s -p "Enter NAS password: " smb_password
            echo
            sudo sh -c "echo 'username=$smb_username\npassword=$smb_password\ndomain=' > /etc/.smbpicreds"
            sudo chmod 600 /etc/.smbpicreds
            sudo chown $USER:$USER /etc/.smbpicreds
            echo "Credential file /etc/.smbpicreds created with read and write access for current user."
            ;;
        3)
            echo "Ignoring. Videos will be stored locally."
            ;;
        *)
            echo "Invalid choice."
            ;;
    esac
else
    echo "Credential file for smbclient found."
    # Check if the credential file has the correct permissions
    if [ "$(stat -c %a /etc/.smbpicreds)" != "600" ]; then
        sudo chmod 600 /etc/.smbpicreds
        sudo chown $USER:$USER /etc/.smbpicreds
        echo "Credential file permissions updated."
    fi
fi

# Modify /etc/dphys-swapfile
echo "Extending swap size to 2GB..."
# It should be 3GB but in practice it is limited to 2GB
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=3072/' /etc/dphys-swapfile

# Add specific sudo privileges for the current user
current_user=$(whoami)
sudoers_entry="${current_user} ALL=(ALL) NOPASSWD: /sbin/poweroff, /sbin/halt, /sbin/reboot, /bin/mount, /bin/umount"

echo "Adding specific sudo privileges for the current user..."
echo "$sudoers_entry" | sudo tee /etc/sudoers.d/$current_user > /dev/null

# Create the udev rule for FT232H
udev_rule_file="/etc/udev/rules.d/99-ftdi.rules"
udev_rule='SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6014", MODE="0666"'

echo "Adding udev rule for FT232H..."
if [ -f "$udev_rule_file" ]; then
    if ! grep -q "$udev_rule" "$udev_rule_file"; then
        echo "$udev_rule" | sudo tee -a "$udev_rule_file" > /dev/null
        echo "FT232H udev rule added."
    else
        echo "FT232H udev rule already exists."
    fi
else
    echo "$udev_rule" | sudo tee "$udev_rule_file" > /dev/null
    echo "FT232H udev rule file created and rule added."
fi

echo
echo "Installation done. Please reboot to apply all the changes."
