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

# ask for confirmation if -y flag is not used
if [ "$yes_flag" = false ]; then
    read -p "Do you want to continue? (y/n): " continue_install
    if [ "$continue_install" != "y" ]; then
        echo "Installation aborted."
        exit 0
    fi
fi

# Display help and exit if -h flag is used
if [ "$help_flag" = true ]; then
    echo "Usage: $(basename $0) [-y] [-h]"
    echo "  -y    Automatically install dependencies without confirmation."
    echo "  -h    Display this help message."
    exit 0
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "Git is not installed. Installing git using apt..."
    
    if [ "$yes_flag" = true ]; then
        sudo apt update
        sudo apt install git -y
    else
        read -p "Do you want to install git? (y/n): " install_git
        if [ "$install_git" = "y" ]; then
            sudo apt update
            sudo apt install git
        fi
    fi
else
    echo "Git installation found."
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Installing python3 using apt..."
    
    if [ "$yes_flag" = true ]; then
        sudo apt update
        sudo apt install python3 -y
    else
        read -p "Do you want to install python3? (y/n): " install_python3
        if [ "$install_python3" = "y" ]; then
            sudo apt update
            sudo apt install python3
        fi
    fi
else
    echo "Python 3 installation found."
fi

# Check if smbclient is installed
if ! command -v smbclient &> /dev/null; then
    echo "smbclient is not installed. Installing smbclient using apt..."

    if [ "$yes_flag" = true ]; then
        sudo apt update
        sudo apt install smbclient -y
    else
        read -p "Do you want to install smbclient? (y/n): " install_smbclient
        if [ "$install_smbclient" = "y" ]; then
            sudo apt update
            sudo apt install smbclient
        fi
    fi
else
    echo "smbclient installation found."
fi

script_path=$(pwd)/cam.py

# Try creating the symbolic link using sudo
if sudo ln -s $script_path /usr/local/bin/picam 2>/dev/null; then
    echo "Symbolic link 'picam' successfully created in /usr/local/bin."
else
    link_status=$?
    if [ $link_status -eq 1 ]; then
      # check if it points to the same file
      if [ "$(readlink /usr/local/bin/picam)" = "$script_path" ]; then
          echo "Symbolic link 'picam' already exists in /usr/local/bin. Nothing to do."
      else
        # delete the existing link and create a new one
        sudo rm /usr/local/bin/picam
        sudo ln -s $script_path /usr/local/bin/picam
        echo "Symbolic link 'picam' successfully created in /usr/local/bin."
      fi

    else
        echo "Failed to create symbolic link. Please check the script path and try again."
    fi
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
    read -p "Do you want to add yourself to these groups? (y/n): " add_to_groups
    if [ "$add_to_groups" = "y" ]; then
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

echo Installing python dependencies...

# Check if opencv is installed
if ! python3 -c "import cv2" &> /dev/null; then
    echo "OpenCV is not installed."
    missing_libs+=("opencv-python")
else
    echo "OpenCV installation found."
fi

# Check if any version of numpy 1.26.* is installed
if ! python3 -c "import re; import numpy; assert re.match(r'1\.26\.\d+', numpy.__version__)" &> /dev/null; then
    echo "numpy 1.26.x is not installed."
    missing_libs+=("numpy==1.26.3")
else
    echo "numpy 1.26.x installation found."
fi
# Check if pandas is installed
if ! python3 -c "import pandas" &> /dev/null; then
    echo "pandas is not installed."
    missing_libs+=("pandas")
else
    echo "pandas installation found."
fi

# Check if picamera2 is installed
if ! python3 -c "import picamera2" &> /dev/null; then
    echo "picamera2 is not installed."
    missing_libs+=("picamera2==0.3.12")
else
    echo "picamera installation found."
fi

# Check if trackpy is installed
if ! python3 -c "import trackpy" &> /dev/null; then
    echo "trackpy is not installed."
    missing_libs+=("trackpy")
else
    echo "trackpy installation found."
fi

# Check if matplotlib is installed
if ! python3 -c "import matplotlib" &> /dev/null; then
    echo "matplotlib is not installed."
    missing_libs+=("matplotlib")
else
    echo "matplotlib installation found."
fi

# Check if tqdm is installed
if ! python3 -c "import tqdm" &> /dev/null; then
    echo "tqdm is not installed."
    missing_libs+=("tqdm")
else
    echo "tqdm installation found."
fi

# Check if there are any missing libraries
if [ ${#missing_libs[@]} -eq 0 ]; then
    echo "All required libraries are already installed."
else
    echo "The following libraries are missing: ${missing_libs[@]}"
    if [ "$yes_flag" = true ]; then
        pip3 install "${missing_libs[@]}"
    else
        read -p "Do you want to install the missing libraries? (y/n): " install_libs
        if [ "$install_libs" = "y" ]; then
            pip3 install "${missing_libs[@]}"
        fi
    fi
fi

# Check if /etc/.smbpicreds exists
if [ ! -f /etc/.smbpicreds ]; then
    echo "No credential file for smbclient was found (/etc/.smbpicreds)."
    read -p "Do you want to:
    1. Locate an existing credential file
    2. Generate /etc/.smbpicreds
    3. Ignore (Videos will be stored locally)
Enter your choice (1/2/3): " smbcred_choice

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
            echo "    to be created for that purpose as credentials will be store as plain text"
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

# Modify /etc/dphys-swapfile
echo "Extending swap size to 2GB..."
# It should be 3GB but in practice it is limited to 2GB
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=3072/' /etc/dphys-swapfile

current_user=$(whoami)
sudoers_entry="${current_user} ALL=(ALL) NOPASSWD: /sbin/poweroff, /sbin/halt, /sbin/reboot, /bin/mount, /bin/umount"

echo "Adding specific sudo privileges for the current user..."
echo "$sudoers_entry" | sudo tee -a /etc/sudoers.d/$current_user > /dev/null

echo
echo
echo "Installation done. Please reboot to apply all the changes."

