from metagpt.tools.tool_registry import register_tool
from metagpt.tools.tool_type import ToolType
from imap_tools import MailBox


@register_tool(tool_type=ToolType.EMAIL_LOGIN.type_name)
def email_login_imap(email_address, email_password):
    """
    Use imap_tools package to log in to your email (the email that supports IMAP protocol) to verify and return the account object.

    Args:
        email_address (str): Email address that needs to be logged in and linked.
        email_password (str): Password for the email address that needs to be logged in and linked.

    Returns:
        object: The imap_tools's MailBox object returned after successfully connecting to the mailbox through imap_tools, including various information about this account (email, etc.), or None if login fails.
    """

    # Define a dictionary mapping email domains to their IMAP server addresses
    imap_servers = {
    'outlook.com': 'imap-mail.outlook.com',  # Outlook
    '163.com': 'imap.163.com',                # 163 Mail
    'qq.com': 'imap.qq.com',                  # QQ Mail
    'gmail.com': 'imap.gmail.com',            # Gmail
    'yahoo.com': 'imap.mail.yahoo.com',       # Yahoo Mail
    'icloud.com': 'imap.mail.me.com',         # iCloud Mail
    'hotmail.com': 'imap-mail.outlook.com',   # Hotmail (同 Outlook)
    'live.com': 'imap-mail.outlook.com',      # Live (同 Outlook)
    'sina.com': 'imap.sina.com',              # Sina Mail
    'sohu.com': 'imap.sohu.com',              # Sohu Mail
    'yahoo.co.jp': 'imap.mail.yahoo.co.jp',   # Yahoo Mail Japan
    'yandex.com': 'imap.yandex.com',          # Yandex Mail
    'mail.ru': 'imap.mail.ru',                # Mail.ru
    'aol.com': 'imap.aol.com',                # AOL Mail
    'gmx.com': 'imap.gmx.com',                # GMX Mail
    'zoho.com': 'imap.zoho.com',              # Zoho Mail
    }

    # Extract the domain from the email address
    domain = email_address.split('@')[-1]

    # Determine the correct IMAP server
    imap_server = imap_servers.get(domain)

    if not imap_server:
        print(f'IMAP server for {domain} not found.')
        return None

    # Attempt to log in to the email account
    try:
        mailbox = MailBox(imap_server).login(email_address, email_password)
        print('Login successful')
        return mailbox
    except Exception as e:
        print(f'Login failed: {e}')
        return None