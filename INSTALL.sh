#!/bin/bash

# Initialize the flags
yes_flag=false
help_flag=false

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

script_path=$(pwd)/cam.py

# Try creating the symbolic link using sudo
if sudo ln -s $script_path /usr/local/bin/picam 2>/dev/null; then
    echo "Symbolic link 'picam' successfully created in /usr/local/bin."
else
    link_status=$?
    if [ $link_status -eq 1 ]; then
        echo "Symbolic link 'picam' already exists in /usr/local/bin. Nothing to do."
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


