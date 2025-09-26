import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") 


def send_email(to: str, subject: str, body: str):
    """
    Send an email using SMTP
    """
    print("Preparing to send email...")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to
    msg['Subject'] = subject

    # Body
    msg.attach(MIMEText(body, 'html'))

    # Send email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to, msg.as_string())
        print(f"Email sent to {to}")
    except Exception as e:
        print(f"Error sending email: {e}")


# if __name__ == "__main__":
#     # Example usage
#     send_email(
#         to="sami606713@gmail.com",
#         subject="Test Email",
#         body="<h1>This is a test email</h1><p>Sent using Python</p>"
#     )