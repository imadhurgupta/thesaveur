from datetime import datetime


def get_email_template(heading, body_content, banner_color_start="#2D5016", banner_color_end="#3A661D"):
    """
    Wrap email content in a lightweight, clean brand layout.
    Designed for 100% primary inbox deliverability without heavy or suspicious attachments.
    """
    current_year = datetime.utcnow().year
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{heading}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #FAF7F2; padding: 24px 12px; margin: 0; color: #222222; -webkit-font-smoothing: antialiased;">
    <div style="max-width: 560px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #EAE6DF; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.03);">
        
        <!-- Header Brand Banner -->
        <div style="background-color: {banner_color_start}; padding: 24px 20px; text-align: center; color: #ffffff;">
            <div style="font-size: 22px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;">THE SAVEUR</div>
            <div style="font-size: 11px; opacity: 0.9; margin-top: 4px; letter-spacing: 0.5px;">Premium Teas & Spices</div>
        </div>

        <!-- Main Body -->
        <div style="padding: 32px 28px; line-height: 1.6;">
            <h2 style="color: #2D5016; margin-top: 0; font-size: 18px; font-weight: 700; margin-bottom: 16px;">{heading}</h2>
            {body_content}
        </div>

        <!-- Security / Transactional Footer -->
        <div style="background-color: #FAF7F2; padding: 18px 24px; text-align: center; font-size: 12px; color: #777777; border-top: 1px solid #EAE6DF;">
            <p style="margin: 0 0 6px 0;">This is an automated transactional security message from <strong>The Saveur</strong>.</p>
            <p style="margin: 0; font-size: 11px; color: #999999;">&copy; {current_year} The Saveur &bull; <a href="https://thesaveur.com" style="color: #2D5016; text-decoration: none;">thesaveur.com</a></p>
        </div>

    </div>
</body>
</html>"""

