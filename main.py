import yfinance as yf
import requests
import os
import smtplib
from email.message import EmailMessage
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER')


def get_stock_data(ticker):
    """Safely fetches stock data with a 5-day buffer to survive weekends/holidays."""
    try:
        # Fetch 5 days of history so we always have at least 2 valid trading days
        hist = yf.Ticker(ticker).history(period="5d").dropna()

        if len(hist) >= 2:
            close_today = hist['Close'].iloc[-1]
            close_yest = hist['Close'].iloc[-2]
            change_pct = ((close_today - close_yest) / close_yest) * 100
            return {"success": True, "price": close_today, "change": change_pct}
        else:
            return {"success": False, "error": "No recent trades"}
    except Exception as e:
        return {"success": False, "error": "Data fetch failed"}


def build_html_table(portfolio, currency_symbol):
    """Builds a beautiful, modern HTML table for the email."""
    html = """
    <table style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; margin-bottom: 30px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <thead>
            <tr style="background-color: #2c3e50; color: #ffffff; text-align: left;">
                <th style="padding: 12px; font-size: 14px; border-radius: 6px 0 0 0;">Asset</th>
                <th style="padding: 12px; font-size: 14px;">Price</th>
                <th style="padding: 12px; font-size: 14px; border-radius: 0 6px 0 0;">24h Change</th>
            </tr>
        </thead>
        <tbody>
    """

    for ticker, name in portfolio.items():
        print(f"Fetching {name} ({ticker})...")  # Helps you debug in the terminal
        data = get_stock_data(ticker)

        if data["success"]:
            price = data["price"]
            change = data["change"]

            # Formatting logic
            price_str = f"{currency_symbol}{price:,.2f}" if price < 1000 else f"{currency_symbol}{price:,.0f}"
            color = "#27ae60" if change >= 0 else "#c0392b"
            emoji = "🟩" if change >= 0 else "🟥"
            change_str = f"<span style='color: {color}; font-weight: bold;'>{change:+.2f}%</span>"

            html += f"""
            <tr style="border-bottom: 1px solid #e0e0e0; background-color: #ffffff;">
                <td style="padding: 12px; font-size: 14px; color: #333;">{emoji} <b>{name}</b> <br/><span style='color:#7f8c8d; font-size:11px;'>{ticker}</span></td>
                <td style="padding: 12px; font-size: 14px; font-weight: bold; color: #2c3e50;">{price_str}</td>
                <td style="padding: 12px; font-size: 14px;">{change_str}</td>
            </tr>
            """
        else:
            # Row format for when a stock is broken/delisted/closed
            html += f"""
            <tr style="border-bottom: 1px solid #e0e0e0; background-color: #fff8f8;">
                <td style="padding: 12px; font-size: 14px; color: #7f8c8d;">⚠️ <b>{name}</b> <br/><span style='font-size:11px;'>{ticker}</span></td>
                <td colspan="2" style="padding: 12px; font-size: 13px; color: #c0392b;"><i>{data['error']}</i></td>
            </tr>
            """

    html += "</tbody></table>"
    return html


def get_news():
    """Tries Google News first, falls back to Yahoo Finance if blocked."""
    print("Fetching top news story...")
    try:
        # 1. Try Google News
        rss_url = "https://news.google.com/rss/search?q=stock+market+finance&hl=en-US&gl=US&ceid=US:en"
        # Modern User-Agent prevents blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(rss_url, headers=headers, timeout=10)

        if response.status_code == 200:
            root = ET.fromstring(response.text)
            item = root.find('./channel/item')
            if item is not None:
                return f"<a href='{item.find('link').text}' style='color: #2980b9; text-decoration: none; font-size: 16px; font-weight: bold;'>{item.find('title').text}</a>"
    except Exception:
        pass

    try:
        # 2. Fallback to Yahoo Finance News
        news = yf.Ticker('SPY').news
        if news:
            return f"<a href='{news[0]['link']}' style='color: #2980b9; text-decoration: none; font-size: 16px; font-weight: bold;'>{news[0]['title']}</a>"
    except Exception:
        pass

    return "<span style='color: #7f8c8d;'>Market news unavailable today.</span>"


def send_email(subject, html_content):
    """Logs into Gmail and sends the styled HTML report."""
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("❌ ERROR: Missing email credentials. Check your .env file or GitHub Secrets.")
        return

    print("Connecting to email server...")
    clean_password = EMAIL_PASSWORD.replace(" ", "")

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    full_html = f"""\
    <!DOCTYPE html>
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
          <h2 style="color: #2c3e50; margin-top: 0; border-bottom: 2px solid #3498db; padding-bottom: 10px;">📈 Your Portfolio Briefing</h2>
          {html_content}
          <p style="font-size: 12px; color: #95a5a6; text-align: center; margin-top: 40px;">
            Automated by your Python GitHub Action Bot.
          </p>
        </div>
      </body>
    </html>
    """
    msg.add_alternative(full_html, subtype='html')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, clean_password)
            smtp.send_message(msg)
        print(f"✅ SUCCESS: Email delivered to {EMAIL_RECEIVER}!")
    except Exception as e:
        print(f"❌ SMTP ERROR: {e}")


def main():
    jse_portfolio = {
        '4SI.JO': '4Sight Holdings',
        'BAC.JO': 'Africa Bitcoin Corp',
        'AFT.JO': 'Afrimat',
        'ISO.JO': 'ASP Isotopes',
        'BCF.JO': 'Bowler Metcalf Ltd',
        'CAA.JO': 'CA Sales Holdings',
        'DNB.JO': 'Deneb Investments Ltd',
        'FTH.JO': 'Frontier Transport Holdings',
        'LSK.JO': 'Lesaka Technology Inc',
        'PBT.JO': 'PBT Holdings',
        'SKA.JO': 'Shuka Minerals'
    }

    us_portfolio = {
        'REXR': 'Rexford Industrial',
        'JD': 'JD.com',
        'STRK': 'Strategy 8 00 Perpetual Strike Prf Shs Series A'
    }

    # Build the report
    date_str = datetime.now().strftime('%A, %B %d, %Y')
    html_body = f"<p style='color: #7f8c8d; font-style: italic; margin-bottom: 25px;'>{date_str}</p>"

    html_body += "<h3 style='color: #27ae60; margin-bottom: 10px;'>🇿🇦 JSE Holdings</h3>"
    html_body += build_html_table(jse_portfolio, "R")

    html_body += "<h3 style='color: #2980b9; margin-bottom: 10px;'>🇺🇸 US Holdings</h3>"
    html_body += build_html_table(us_portfolio, "$")

    html_body += "<div style='background-color: #f8f9fa; padding: 15px; border-left: 4px solid #f39c12; margin-top: 30px;'>"
    html_body += f"<h3 style='margin-top: 0; color: #333;'>📰 Top Market Headline</h3>{get_news()}</div>"

    # Send the report
    send_email(f"Portfolio Update - {date_str}", html_body)


if __name__ == "__main__":
    main()