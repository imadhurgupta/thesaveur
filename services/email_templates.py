def get_email_template(heading, body_content, banner_color_start="#2D5016", banner_color_end="#5a9e35"):
    """Wrap content in brand-styled HTML email layout."""
    return f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background: linear-gradient(135deg, {banner_color_start} 0%, {banner_color_end} 100%); padding: 30px; text-align: center; color: #ffffff;">
                <img src="cid:logo" alt="The Saveur" style="height: 60px; width: 60px; border-radius: 50%; object-fit: cover; border: 2px solid #ffffff; margin-bottom: 10px;" />
                <h1 style="margin: 5px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold; letter-spacing: 1px;">The Saveur</h1>
            </div>
            <div style="padding: 40px 30px; line-height: 1.6;">
                <h2 style="color: {banner_color_start}; margin-top: 0; font-size: 20px;">{heading}</h2>
                {body_content}
            </div>
            <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
            </div>
        </div>
    </body>
    </html>
    """
