import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

smtp_port = "25"
smtp_server = "smtp.163.com"
sender_mail = "xxx@163.com"
sender_pw = "xxx"
recipients = ["dev@example.com"]

def send_alert(title, message_body):
    # 创建一个 MIMEMultipart 邮件
    message = MIMEMultipart("alternative")
    message["Subject"] = title
    message["From"] = sender_mail
    message["To"] = ", ".join(recipients)

    # 正文部分
    body = f"{message_body}"  # 这是你实际要发送的 HTML 或文本内容
    message.attach(MIMEText(body, "html"))  # 附加 HTML 正文

    # 使用 TLS 启动安全的 SMTP 连接
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls(context=context)
        server.login(sender_mail, sender_pw)
        server.sendmail(sender_mail, recipients, message.as_string())

if __name__ == "__main__":
    print(f"Running script at {datetime.now()}")
    send_alert("This message is sent every 30 minutes", "<h1>Hello World from a Docker container</h1>")