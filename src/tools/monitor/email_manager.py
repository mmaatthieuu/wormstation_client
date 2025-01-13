from dotenv import load_dotenv
import os
import re
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from chardet import detect  # Install using: pip install chardet



IGNORED_FOLDERS_FILE = "ignored_folders.txt"
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


class EmailClient:
    """
    Handles email server connections and operations.
    """
    def __init__(self, email_user, email_password, recipient_list='recipient_list.txt'):
        self.email_user = email_user
        self.email_password = email_password
        self.imap_connection = None

        self.recipient_list = self.load_recipient_list(recipient_list)

    def load_recipient_list(self, recipient_list_file):
        """
        Loads recipient email addresses from a file.
        """
        if not os.path.exists(recipient_list_file):
            print(f"Recipient list file not found: {recipient_list_file}")
            return []
        with open(recipient_list_file, "r") as f:
            # If the file is empty, print a warning and return an empty list
            if f.read().strip() == "":
                print("Recipient list file is empty.")
                return []
            return [line.strip() for line in f]


    def connect_imap(self):
        """Connects to the IMAP server and logs in."""
        self.imap_connection = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        self.imap_connection.login(self.email_user, self.email_password)

    def fetch_emails(self, mailbox="inbox"):
        """Fetches all emails from the specified mailbox."""
        self.imap_connection.select(mailbox)
        _, search_data = self.imap_connection.search(None, "ALL")
        messages = []
        for num in search_data[0].split():
            _, data = self.imap_connection.fetch(num, "(RFC822)")
            raw_email = data[0][1]
            messages.append(email.message_from_bytes(raw_email))
        return messages

    def disconnect_imap(self):
        """Logs out from the IMAP server."""
        if self.imap_connection:
            self.imap_connection.logout()

    def send_email(self, recipient, subject, body):
        """Sends an email using SMTP."""
        msg = MIMEMultipart()
        msg["From"] = self.email_user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.sendmail(self.email_user, recipient, msg.as_string())

    def send_email_to_all(self, subject, body):
        """
        Sends an email to all recipients in the recipient list.
        If the recipient list is empty, logs a message and returns.
        """
        if not hasattr(self, "recipient_list") or not self.recipient_list:
            print("Recipient list is empty. No emails will be sent.")
            return

        for recipient in self.recipient_list:
            self.send_email(recipient, subject, body)


class EmailHandler:
    """
    Processes email replies and extracts specific instructions.
    """

    def __init__(self, email_client, root_directory="/path/to/recordings"):
        self.email_client = email_client
        self.root_directory = os.path.abspath(root_directory)

    def process_emails(self):
        """
        Processes emails to extract and handle IGNORE instructions.
        """
        messages = self.email_client.fetch_emails()
        ignored_folders = []

        for msg in messages:
            # Extract email content
            body = self._get_email_body(msg)

            # Look for IGNORE instructions
            if body and "IGNORE:" in body:
                start_index = body.find("IGNORE:") + len("IGNORE:")
                device_path = body[start_index:].strip().split()[0]

                # Validate the extracted path
                if self._is_valid_path(device_path):
                    ignored_folders.append(device_path)
                else:
                    print(f"Invalid path received: {device_path}")

        return ignored_folders

    @staticmethod
    def _get_email_body(msg):
        """
        Extracts the plain text body from an email message.

        :param msg: Email message object.
        :return: Plain text body content.
        """
        def decode_content(content):
            # Detect encoding and decode content
            try:
                detected_encoding = detect(content)["encoding"]
                return content.decode(detected_encoding or "utf-8", errors="replace")
            except Exception:
                return content.decode("utf-8", errors="replace")

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    content = part.get_payload(decode=True)
                    return decode_content(content)
        else:
            content = msg.get_payload(decode=True)
            return decode_content(content)

    def _is_valid_path(self, path):
        """
        Validates the extracted path to ensure it is safe and well-formed.

        :param path: The extracted path from the email.
        :return: True if the path is valid, False otherwise.
        """
        # Ensure the path is absolute
        path = os.path.abspath(path)

        # # Ensure the path is within the allowed root directory
        # if not path.startswith(self.root_directory):
        #     print(f"Path {path} is outside the allowed root directory.")
        #     return False

        # Prevent directory traversal (e.g., "../" or similar patterns)
        if ".." in path or not re.match(r"^[a-zA-Z0-9_\-/\\.+:=,]+$", path):
            print(f"Path {path} contains invalid characters or traversal patterns.")
            return False

        # # Optionally, check if the path exists on the file system
        # if not os.path.exists(path):
        #     print(f"Path {path} does not exist.")
        #     return False

        return True


class IgnoredFoldersManager:
    """
    Manages the list of ignored folders.
    """

    def __init__(self, ignored_folders_file):
        self.ignored_folders_file = ignored_folders_file

    def update(self, email_client):
        """
        Updates the ignored folders list based on email instructions.

        :param email_handler: EmailHandler instance to process emails.
        """

        email_handler = EmailHandler(email_client)

        # Process emails for IGNORE instructions
        ignored_folders = email_handler.process_emails()
        for folder in ignored_folders:
            self.add_ignored_folder(folder)

    def load_ignored_folders(self):
        """
        Loads the list of ignored folders from the file.

        :return: Set of ignored folder paths.
        """
        if not os.path.exists(self.ignored_folders_file):
            return set()
        with open(self.ignored_folders_file, "r") as f:
            return set(line.strip() for line in f)

    def save_ignored_folders(self, ignored_folders):
        """
        Saves the list of ignored folders to the file.

        :param ignored_folders: Set of ignored folder paths.
        """
        with open(self.ignored_folders_file, "w") as f:
            for folder in ignored_folders:
                f.write(folder + "\n")

    def add_ignored_folder(self, folder_path):
        """
        Adds a folder to the ignored folders list.

        :param folder_path: Path of the folder to ignore.
        """
        ignored_folders = self.load_ignored_folders()
        if folder_path not in ignored_folders:
            ignored_folders.add(folder_path)
            self.save_ignored_folders(ignored_folders)
            print(f"Added {folder_path} to ignored folders.")


# Main Workflow
if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    print(EMAIL_USER)

    if not EMAIL_USER or not EMAIL_PASSWORD:
        raise ValueError("Email credentials are missing. Please set them in environment variables or a .env file.")

    # Initialize components
    email_client = EmailClient(EMAIL_USER, EMAIL_PASSWORD)
    ignored_manager = IgnoredFoldersManager(IGNORED_FOLDERS_FILE)
    email_handler = EmailHandler(email_client)

    try:
        # Connect to IMAP server
        email_client.connect_imap()

        # Process emails for IGNORE instructions
        ignored_folders = email_handler.process_emails()
        for folder in ignored_folders:
            ignored_manager.add_ignored_folder(folder)

        # Print ignored folders
        print("Ignored folders:", ignored_manager.load_ignored_folders())

    except Exception as e:
        print(f"Error: {e}")

    finally:
        # Disconnect from IMAP server
        email_client.disconnect_imap()
