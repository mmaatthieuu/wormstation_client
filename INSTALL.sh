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


# Check if user is part of gpio group
if ! groups | grep -q '\bgpio\b'; then
    read -p "You are not part of the 'gpio' group. This is required to properly run Wormstation-client. Do you want to add yourself to the group? (y/n): " add_to_gpio
    if [ "$add_to_gpio" = "y" ]; then
        sudo usermod -aG gpio $USER
        echo "Added user to 'gpio' group. Changes will take effect after logging out and back in."
    fi
else
    echo "User is already part of the 'gpio' group."
fi

# Check if user is part of video group
if ! groups | grep -q '\bvideo\b'; then
    read -p "You are not part of the 'video' group. This is required to properly run Wormstation-client. Do you want to add yourself to the group? (y/n): " add_to_video
    if [ "$add_to_video" = "y" ]; then
        sudo usermod -aG video $USER
        echo "Added user to 'video' group. Changes will take effect after logging out and back in."
    fi
else
    echo "User is already part of the 'video' group."
fi

# Check if user is part of input group
if ! groups | grep -q '\binput\b'; then
    read -p "You are not part of the 'input' group. This is required to properly run Wormstation-client. Do you want to add yourself to the group? (y/n): " add_to_input
    if [ "$add_to_input" = "y" ]; then
        sudo usermod -aG input $USER
        echo "Added user to 'input' group. Changes will take effect after logging out and back in."
    fi
else
    echo "User is already part of the 'input' group."
fi

echo Installing python dependencies...

# Check if opencv is installed
if ! python3 -c "import cv2" &> /dev/null; then
    echo "OpenCV is not installed. Installing opencv using pip..."
    
    if [ "$yes_flag" = true ]; then
        pip3 install opencv-python
    else
        read -p "Do you want to install opencv? (y/n): " install_opencv
        if [ "$install_opencv" = "y" ]; then
            pip3 install opencv-python
        fi
    fi
else
    echo "OpenCV installation found."
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
fi

# Modify /etc/dphys-swapfile
echo "Extending swap size to 2GB..."
# It should be 3GB but in practice it is limited to 2GB
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=3072/' /etc/dphys-swapfile

echo
echo
echo "Installation done. Please reboot to apply all the changes."

