from app import create_app
from extensions import db
from models import User

app = create_app()
with app.app_context():
    admin = User.query.filter_by(email="admin@wsas.com").first()
    if admin:
        admin.is_email_verified = True
        from werkzeug.security import generate_password_hash
        # Ensure password is Admin@123
        admin.password_hash = generate_password_hash("Admin@123")
        db.session.commit()
        print("Admin user verified successfully!")
    else:
        print("Admin not found!")
